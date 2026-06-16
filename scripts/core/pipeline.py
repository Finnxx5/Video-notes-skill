# coding: utf-8

import os, sys, time, traceback, re
from pathlib import Path
from typing import Optional, Callable

from models.types import VideoAnalysis, PipelineResult, TopicSegment, TranscriptSegment
from platforms.base import detect
from platforms.bilibili import BilibiliDownloader
from platforms.douyin import DouyinDownloader
from platforms.local import LocalDownloader
from core.transcriber import transcribe, format_transcript_timed, estimate_transcript_quality
from core.segmenter import segment_transcript, fill_transcript_in_segments
from core.anchor_builder import build_anchors, get_all_anchors, anchor_stats
from core.frame_collector import collect_frames, collect_stats
from core.frame_analyst import classify_and_describe, save_vlm_report
from core.note_writer import generate_note

def _safe_write(filepath, content):
    """Write file, ensuring parent dir exists (retry 3x)."""
    import time as _t
    d = Path(filepath).parent
    for _ in range(3):
        try:
            d.mkdir(parents=True, exist_ok=True)
            Path(filepath).write_text(content, encoding="utf-8")
            return
        except Exception:
            _t.sleep(0.1)
    Path(filepath).write_text(content, encoding="utf-8")  # Last attempt, let it raise



def _load_bilibili_subtitle(sub_path):
    """Convert B站 subtitle file to timed_text + segments."""
    if not sub_path or not Path(sub_path).exists():
        return None, None, None
    lines = Path(sub_path).read_text(encoding="utf-8").strip().split("\n")
    timed_lines = []
    segments = []
    for line in lines:
        m = re.match(r'\[(\d+):(\d+)\] (.+)', line)
        if m:
            minutes, seconds, text = int(m.group(1)), int(m.group(2)), m.group(3).strip()
            start = minutes * 60 + seconds
            timed_lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")
            segments.append(TranscriptSegment(start=float(start), end=float(start + 3), text=text, words=[]))
    timed_text = "\n".join(timed_lines)
    return timed_text, segments, len(segments)


async def run_pipeline(
    video_url, api_key, base_url,
    vlm_model="Qwen/Qwen3-VL-8B-Instruct",
    llm_model="moonshotai/Kimi-K2.5",
    asr_model="base", asr_language="zh", llm_fallback="", vlm_fallback="", output_base="output",
    skip_download=False, skip_asr=False, skip_notes=False,
    progress_cb=None,
):
    result = PipelineResult(success=False, video_name="")
    stats = {}
    try:
        # ── Download ──
        if not skip_download:
            platform = detect(video_url)
            if not platform:
                result.error = f"unknown: {video_url}"; return result
            od = Path(output_base)
            od.mkdir(parents=True, exist_ok=True)
            dl = {"bilibili": BilibiliDownloader, "douyin": DouyinDownloader, "local": LocalDownloader}[platform](od)
            video_path, video_name, sub_path = await dl.download(video_url)
            if not video_path:
                result.error = f"download fail: {video_name}"; return result
            result.video_path, result.video_name = video_path, video_name
        else:
            result.video_name = Path(video_url).stem
            video_path = video_url; result.video_path = video_path
            sub_path = None

        vn = result.video_name
        # Sanitize: ensure output dir name is safe ASCII only
        vn = re.sub(r'[^\x00-\x7F]', '', vn)
        vn = re.sub(r'[<>:"/\\|?*]', '_', vn)
        vn = re.sub(r'[+&,%$#@!~`\'=()\[\]{}]', '_', vn)  # strip special chars
        vn = re.sub(r'\s+', '_', vn).strip('._ ')
        vn = vn or 'video_note'
        result.video_name = vn
        od = Path(output_base) / vn
        od.mkdir(parents=True, exist_ok=True)
        result.output_dir = od

        # ── Transcript: B站字幕 → ASR ──
        ts_segments = []
        timed_text = None

        # Try B站 subtitles first
        if sub_path:
            print("  [Subtitle...]", end=" ")
            timed_text, ts_segments, n = _load_bilibili_subtitle(sub_path)
            if timed_text:
                _safe_write(od / "transcript.txt", timed_text)
                print(f"{n} lines from B站 subtitles")
                stats["asr_segments"] = n
                stats["asr_time"] = 0
                stats["subtitle_source"] = "bilibili"

        # Fallback to ASR
        if not timed_text and not skip_asr:
            print("  [ASR...]")
            audio_path = video_path
            candidate_audio = od / f"{vn}_audio.m4a"
            if candidate_audio.exists() and candidate_audio.stat().st_size > 100000:
                audio_path = str(candidate_audio)
                print(f"  Using audio track")
            t0 = time.time()
            ts_segments, full_text = transcribe(audio_path, model_name=asr_model, language=asr_language)
            quality = estimate_transcript_quality(ts_segments)
            timed_text = format_transcript_timed(ts_segments)
            _safe_write(od / "transcript.txt", timed_text)
            stats["asr_time"] = round(time.time() - t0, 1)
            stats["asr_segments"] = len(ts_segments)
            stats["subtitle_source"] = "asr"
            print(f"  ASR: {len(ts_segments)} segments, conf={quality['confidence']:.2f}")

        if not timed_text:
            tf = od / "transcript.txt"
            if tf.exists():
                timed_text = tf.read_text(encoding="utf-8")
            else:
                result.error = "no transcript"; return result

        # ── Segment ──
        print("  [Segmenting...]")
        segments, video_type, video_title = await segment_transcript(timed_text, api_key=api_key, base_url=base_url, model=llm_model, fallback=llm_fallback)
        segments = fill_transcript_in_segments(segments, timed_text)
        stats["segments_count"] = len(segments); stats["video_type"] = video_type
        print(f"  Segments: {len(segments)}, type: {video_type}")

        # ── Anchors ──
        segments = build_anchors(segments, transcript_segments=ts_segments)
        all_anchors = get_all_anchors(segments)
        stats["total_anchors"] = len(all_anchors)
        print(f"  Anchors: {len(all_anchors)}")

        # ── Frames ──
        if all_anchors:
            segments = collect_frames(video_path, segments, str(od))
            fs = collect_stats(segments)
            stats["frames_collected"] = fs["valid_frames"]
        else:
            stats["frames_collected"] = 0

        # ── VLM ──
        analysis = VideoAnalysis(title=video_title or vn, summary="", video_type=video_type, segments=segments, raw_transcript=timed_text, total_anchors=len(all_anchors))
        if analysis.total_anchors > 0:
            print("  [VLM analysis...]")
            analysis = await classify_and_describe(analysis, api_key=api_key, base_url=base_url, vlm_model=vlm_model, vlm_fallbacks=[vlm_fallback] if vlm_fallback else None)
            vlm_report = save_vlm_report(analysis, str(od))
            print(f"  VLM report: {vlm_report.name}")

        # ── Notes ──
        if not skip_notes:
            print("  [Writing notes...]")
            note = await generate_note(analysis, api_key=api_key, base_url=base_url, llm_model=llm_model, fallback=llm_fallback)
            np = od / "node.md"; _safe_write(np, note)
            result.note_path = np

        result.success = True; result.analysis = analysis; result.stats = stats
    except Exception as e:
        result.error = str(e); traceback.print_exc()
    return result
