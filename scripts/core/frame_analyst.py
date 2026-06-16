import json, asyncio, sys, os
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
from models.types import Frame, VideoAnalysis
from prompts.frame_classifier import SCREEN_SYSTEM, SCREEN_USER_TEMPLATE, DESCRIBE_SYSTEM, DESCRIBE_USER_TEMPLATE
from utils.image import encode_base64

VLM_CC = 6
DESCRIBE_CC = 2

async def classify_and_describe(analysis, api_key, base_url, vlm_model, vlm_fallbacks=None):
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    fb = vlm_fallbacks or []
    all_frames = [(s, f) for s in analysis.segments for f in s.frames if f.path and Path(f.path).exists()]
    if not all_frames:
        print("  VLM: no frames"); return analysis
    print(f"  VLM: classifying {len(all_frames)} frames...")
    await _classify_batch(client, all_frames, vlm_model, fb, analysis)
    bf = [(s,f) for s,f in all_frames if f.classification=="B"]
    cf = [(s,f) for s,f in all_frames if f.classification=="C"]
    print(f"  VLM: B={len(bf)}, C={len(cf)}")
    if bf: await _describe_batch(client, bf, vlm_model, fb, is_c=False)
    if cf: await _describe_batch(client, cf, vlm_model, fb, is_c=True)
    # Dedup: downgrade consecutive C frames in same segment if too close
    _dedup_c_frames(analysis)
    analysis.total_frames_collected = len(all_frames)
    bf2 = [(s,f) for s in analysis.segments for f in s.frames if f.classification=="B"]
    cf2 = [(s,f) for s in analysis.segments for f in s.frames if f.classification=="C"]
    analysis.total_frames_kept = len(bf2) + len(cf2)
    print(f"  After dedup: A={analysis.total_frames_collected-analysis.total_frames_kept}, B={len(bf2)}, C={len(cf2)}")
    return analysis

async def _vlm_call(client, messages, model, fallbacks, max_tokens=1024):
    for m in [model] + [f for f in fallbacks if f != model]:
        for a in range(3):
            try:
                r = await client.chat.completions.create(model=m, messages=messages, max_tokens=max_tokens)
                return r.choices[0].message.content
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower(): break
                if a < 2: await asyncio.sleep(2**a)
    return ""

async def _classify_one(seg, frame, client, model, fallbacks, sem):
    async with sem:
        ctx = SCREEN_USER_TEMPLATE.format(segment_title=seg.title, segment_summary=seg.summary, scene_guess=frame.scene_guess or "unknown", time_str=frame.time_str)
        b64 = encode_base64(frame.path)
        msgs = [{"role":"system","content":SCREEN_SYSTEM},{"role":"user","content":[{"type":"text","text":ctx},{"type":"image_url","image_url":{"url":b64}}]}]
        try:
            ct = await _vlm_call(client, msgs, model, fallbacks, max_tokens=256)
            for ln in ct.strip().split("\n"):
                if "{" in ln:
                    try: frame.classification = json.loads(ln).get("class","A"); return
                    except: pass
            frame.classification = "C"
        except: frame.classification = "C"

def _clean_vlm_output(text):
    """Strip B-frame:/C-frame: prefixes and markdown artifacts from VLM output."""
    import re
    text = text.strip()
    # Remove leading B-frame:/C-frame: prefixes
    text = re.sub(r"^(B-frame|C-frame|A-frame)\s*[:\-]?\s*", "", text, flags=re.IGNORECASE)
    # Remove leading ** B-Frame / ** C-Frame style markers
    text = re.sub(r"^\*\*\s*(B-Frame|C-Frame|A-Frame)\s*\*\*\s*[:\-]?\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


async def _describe_one(seg, frame, client, model, fallbacks, sem, is_c):
    async with sem:
        p = f"Frame at {frame.time_str}."
        if seg.transcript_text: p += f"\n\nTranscript:\n{seg.transcript_text[:300]}"
        b64 = encode_base64(frame.path)
        msgs = [{"role":"system","content":DESCRIBE_SYSTEM},{"role":"user","content":[{"type":"text","text":p},{"type":"image_url","image_url":{"url":b64}}]}]
        try:
            ct = await _vlm_call(client, msgs, model, fallbacks, max_tokens=2048)
            ct = _clean_vlm_output(ct) if ct else ct
            ok = bool(ct and ct.strip())
            if is_c:
                frame.description = ct if ok else f"[Screenshot: {frame.time_str}]"
            else:
                frame.extracted_text = ct if ok else ""
            return ok
        except:
            if is_c: frame.description = f"[Screenshot: {frame.time_str}]"
            else: frame.extracted_text = ""
            return False

def _dedup_c_frames(analysis, max_c_per_seg=2, min_interval=10.0):
    """Limit C frames per segment, keep best-spaced ones."""
    for seg in analysis.segments:
        c_indices = [i for i, f in enumerate(seg.frames) if f.classification == "C"]
        if len(c_indices) <= max_c_per_seg:
            continue
        # Keep frames with best time spacing (evenly distributed)
        c_frames = [seg.frames[i] for i in c_indices]
        # Sort by time, pick evenly spaced
        times = [f.time for f in c_frames]
        t_min, t_max = times[0], times[-1]
        if t_max - t_min < 5:
            # All clumped together, keep first only
            for f in c_frames[1:]:
                f.classification = "A"
            continue
        # Pick evenly spaced frames up to max_c_per_seg
        n = min(max_c_per_seg, len(times))
        if n >= len(times):
            continue
        step = (len(times) - 1) / (n - 1) if n > 1 else 1
        keep_times = {times[min(int(i * step), len(times)-1)] for i in range(n)}
        for f in c_frames:
            if f.time not in keep_times:
                f.classification = "A"


async def _classify_batch(c, frames, model, fb, analysis):
    sem = asyncio.Semaphore(VLM_CC)
    await asyncio.gather(*[_classify_one(s, f, c, model, fb, sem) for s, f in frames])


def save_vlm_report(analysis, output_dir):
    """Save per-frame VLM results to vlm_analysis.md"""
    lines = ["# VLM Frame Analysis", "", f"Video: {analysis.title}", f"Type: {analysis.video_type}",
             f"Total frames: {analysis.total_frames_collected}", ""]

    for seg in analysis.segments:
        if not seg.frames:
            continue
        lines.append("---")
        lines.append(f"## {seg.title} ({_fmt_time(seg.start)} - {_fmt_time(seg.end)})")
        lines.append(f"> {seg.summary}")
        lines.append("")

        for frame in seg.frames:
            cls_label = {"A": "舍弃", "B": "提取信息", "C": "保留原图"}.get(frame.classification, "unknown")
            lines.append(f"### [{cls_label}] {frame.time_str}")
            rel_path = Path(frame.path).name if frame.path else ""
            lines.append(f"![](imgs/{rel_path})")
            lines.append("")

            if frame.classification == "B" and frame.extracted_text:
                lines.append("**提取信息:**")
                lines.append("```")
                lines.append(frame.extracted_text.strip())
                lines.append("```")
            elif frame.classification == "C" and frame.description:
                lines.append(f"**画面描述:** {frame.description.strip()}")
            elif frame.classification == "A":
                lines.append("**原因:** 重复/模糊/无信息量")
            lines.append("")

    out_path = Path(output_dir) / "vlm_analysis.md"
    out_path.write_text(os.linesep.join(lines), encoding="utf-8")
    return out_path


def _fmt_time(seconds):
    m, s = int(seconds) // 60, int(seconds) % 60
    return f"{m:02d}:{s:02d}"


async def _describe_batch(c, frames, model, fb, is_c):
    sem = asyncio.Semaphore(DESCRIBE_CC)
    results = await asyncio.gather(*[_describe_one(s, f, c, model, fb, sem, is_c) for s, f in frames], return_exceptions=True)
    ok = sum(1 for r in results if r is True)
    print(f"  Describe: {ok}/{len(frames)} OK")
