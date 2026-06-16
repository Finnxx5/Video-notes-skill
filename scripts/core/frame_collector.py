"""
目标帧采集器

根据锚点时间戳列表，精准截取帧。
使用外部 ffmpeg 进程，而非 cv2.imwrite。
"""

import os
import sys
from pathlib import Path
from typing import Optional, Callable

from models.types import TopicSegment, Frame, AnchorTypeStr
from utils.ffmpeg import capture_frame
from utils.image import encode_base64


ANCHOR_TYPE_MAP: dict[str, AnchorTypeStr] = {
    "llm_annotated": "llm_annotated",
    "segment_start": "segment_start",
    "segment_mid": "segment_mid",
    "pause_detected": "pause_detected",
}


def collect_frames(
    video_path: str,
    segments: list[TopicSegment],
    output_dir: str,
    progress_cb: Optional[Callable] = None,
) -> list[TopicSegment]:
    """
    为每个 Segment 的锚点截取帧。
    """
    frames_dir = Path(output_dir) / "imgs"
    os.makedirs(frames_dir, exist_ok=True)

    all_targets = []
    for seg in segments:
        for ts in seg.anchors:
            all_targets.append({"time": ts, "segment_id": seg.id})

    if not all_targets:
        return segments

    seg_counters = {seg.id: 0 for seg in segments}
    total = len(all_targets)

    # Build scene_guess lookup: closest visual_moment for each anchor time
    guess_map = {}  # (seg_id, anchor_time) -> scene_guess
    for seg in segments:
        for vm in seg.visual_moments:
            if vm.scene_guess:
                for anchor in seg.anchors:
                    if abs(anchor - vm.time) < 3.0:
                        guess_map[(seg.id, anchor)] = vm.scene_guess

    for idx, target in enumerate(all_targets):
        ts = target["time"]
        seg_id = target["segment_id"]
        mm = int(ts) // 60
        ss = int(ts) % 60
        time_str = f"{mm:02d}:{ss:02d}"

        seg_counters[seg_id] += 1
        filename = f"s{seg_id:02d}_a{seg_counters[seg_id]:02d}_{time_str.replace(':', '_')}.jpg"
        out_path = str(frames_dir / filename)

        success = capture_frame(video_path, ts, out_path)

        # Look up scene_guess for this anchor
        scene_guess = guess_map.get((seg_id, ts), "")

        for seg in segments:
            if seg.id == seg_id:
                frame = Frame(
                    time=ts, time_str=time_str, path=out_path if success else "",
                    segment_id=seg_id, anchor_type="llm_annotated",
                    scene_guess=scene_guess,
                )
                seg.frames.append(frame)
                break

        if progress_cb:
            progress_cb(idx + 1, total)

    for seg in segments:
        seg.frames = [f for f in seg.frames if f.path and Path(f.path).exists()]

    return segments


def collect_stats(segments: list[TopicSegment]) -> dict:
    total = sum(len(s.frames) for s in segments)
    valid = sum(len([f for f in s.frames if f.path]) for s in segments)
    return {
        "segments_count": len(segments),
        "total_frames": total,
        "valid_frames": valid,
        "failed_frames": total - valid,
    }
