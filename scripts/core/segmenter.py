import json, sys, re
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
from models.types import TopicSegment, VisualMoment
from prompts.segmenter import SEGMENTER_SYSTEM, SEGMENTER_USER_TEMPLATE

def _parse_time(val):
    """Parse MM:SS or seconds to float."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        if ":" in val:
            parts = val.strip().split(":")
            return int(parts[0]) * 60 + float(parts[1])
        try:
            return float(val)
        except:
            return 0.0
    return 0.0

async def segment_transcript(transcript_text, api_key, base_url, model="moonshotai/Kimi-K2.5", fallback="", max_retries=2):
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    prompt = SEGMENTER_USER_TEMPLATE.format(transcript_text=transcript_text)
    fb_list = fallback if isinstance(fallback, list) else ([fallback] if fallback else [])
    models_to_try = [model] + [m for m in fb_list if m and m != model]
    max_retries = len(models_to_try) * 2  # 2 attempts per model
    for attempt in range(max_retries):
        current_model = models_to_try[min(attempt, len(models_to_try)-1)]
        try:
            resp = await client.chat.completions.create(model=current_model, messages=[{"role":"system","content":SEGMENTER_SYSTEM},{"role":"user","content":prompt}], max_tokens=4096, temperature=0.1)
            if not resp.choices or not resp.choices[0].message.content: raise ValueError('Empty API response')
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("`"): raw = raw.split("\n",1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("`"): raw = raw[:-3]
            data = json.loads(raw.strip())
            segs = []
            for i, sd in enumerate(data.get("segments",[])):
                moments = []
                for m in sd.get("visual_moments", []):
                    if not isinstance(m, dict) or "time" not in m:
                        continue
                    moments.append(VisualMoment(
                        time=_parse_time(m["time"]),
                        reason=m.get("reason", ""),
                        moment_type=m.get("type", "must_keep"),
                        scene_guess=m.get("scene_guess", "")
                    ))
                if moments:
                    guesses = [m.scene_guess for m in moments if m.scene_guess]
                    if not guesses:
                        print(f"  WARN: seg {i+1} has {len(moments)} moments but 0 scene_guesses")
                segs.append(TopicSegment(id=i+1, title=sd.get("title",f"Seg{i+1}"), start=_parse_time(sd.get("start",0)), end=_parse_time(sd.get("end",0)), summary=sd.get("summary",""), visual_moments=moments))
            return segs, data.get("type","other"), data.get("title","") or data.get("summary","")
        except Exception as e:
            print(f"  Segmenter attempt {attempt+1} error: {e}")
            # traceback suppressed
            if attempt < max_retries-1:
                import asyncio; await asyncio.sleep(2**attempt)
            continue
    raise RuntimeError(f"Segmentation failed after {max_retries} retries")

def fill_transcript_in_segments(segments, transcript_text):
    lines = []
    for l in transcript_text.split("\n"):
        l = l.strip()
        if l.startswith("["):
            try:
                ts = l.split("]",1)[0][1:]
                txt = l.split("]",1)[1].strip()
                mm, ss = ts.split(":")
                lines.append({"time":int(mm)*60+int(ss), "text":txt})
            except: pass
    for seg in segments:
        seg.transcript_text = "\n".join([x["text"] for x in lines if seg.start <= x["time"] <= seg.end])
    return segments
