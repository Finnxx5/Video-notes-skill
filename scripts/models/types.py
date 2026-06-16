from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path

MomentType = Literal["must_keep", "text_extract", "code_extract", "table_extract"]
VideoType = Literal["tutorial", "news", "lecture", "documentary", "other"]
FrameClass = Literal["A", "B", "C"]
AnchorTypeStr = Literal["llm_annotated", "segment_start", "segment_mid", "pause_detected"]

@dataclass
class WordTimestamp:
    word: str; start: float; end: float; probability: float = 0.0

@dataclass
class TranscriptSegment:
    start: float; end: float; text: str; words: list = field(default_factory=list)

@dataclass
class VisualMoment:
    time: float; reason: str; moment_type: MomentType = "must_keep"; scene_guess: str = ""

@dataclass
class TopicSegment:
    id: int; title: str; start: float; end: float; summary: str
    transcript_text: str = ""
    visual_moments: list = field(default_factory=list)
    anchors: list = field(default_factory=list)
    frames: list = field(default_factory=list)

@dataclass
class Frame:
    time: float; time_str: str; path: str
    segment_id: int = 0
    classification: Optional[FrameClass] = None
    extracted_text: str = ""
    description: str = ""
    anchor_type: AnchorTypeStr = "llm_annotated"
    scene_guess: str = ""

@dataclass
class VideoAnalysis:
    title: str; summary: str; video_type: VideoType = "other"
    segments: list = field(default_factory=list)
    raw_transcript: str = ""
    total_anchors: int = 0
    total_frames_collected: int = 0
    total_frames_kept: int = 0

@dataclass
class PipelineResult:
    success: bool; video_name: str
    video_path: Optional[str] = None
    output_dir: Optional[Path] = None
    note_path: Optional[Path] = None
    analysis: Optional[VideoAnalysis] = None
    error: str = ""
    stats: dict = field(default_factory=dict)
