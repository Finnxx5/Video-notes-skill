---
name: video-notes-skill
description: >
---

# Video-to-Notes

Convert any video URL into a polished Markdown note with screenshots and structured content.

## Quick Start

1. Copy `.env.example` to `.env` and fill in `MODELSCOPE_API_KEY`
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `$env:PYTHONUNBUFFERED=1; python scripts/main.py "<video-url>"`
   (PYTHONUNBUFFERED=1 is **required** to see real-time output in Trae sandbox)

## Supported Platforms

- **Bilibili** (bilibili.com) — Direct API (no cookie needed for most videos; if HTTP 412 occurs, put your cookies in `Cookies/bilibili_cookies.json`)
- **Douyin** (douyin.com) — No cookie needed, yt-dlp
- **Local files** — .mp4, .flv, .mkv, .webm, .avi, .mov

## Workflow

1. **Download** — Fetch video from platform
2. **ASR** — Transcribe audio with faster-whisper
3. **Segment** — LLM splits transcript into topic sections
4. **Frame Capture** — Extract key frames at anchor points
5. **VLM Analysis** — Vision model classifies frames (keep/extract/discard)
6. **Note Generation** — LLM synthesizes transcript + visual context into notes

## Output

- `视频名称/node.md` — Final structured note in simplified Chinese
- `视频名称/imgs/` — Screenshots referenced in node.md are **kept**
- Intermediate files (video, audio, unreferenced frames) are **auto-deleted** after successful generation
- Use `--keep-temp` flag to preserve all intermediate files for debugging

## Commands

```bash
# Full pipeline
$env:PYTHONUNBUFFERED=1; python scripts/main.py "https://www.bilibili.com/video/BV16zDfBtECQ"

# Skip ASR (reuse cached transcript)
$env:PYTHONUNBUFFERED=1; python scripts/main.py "https://v.douyin.com/EGqyDnirXU8/" --skip-asr

# Keep intermediate files
$env:PYTHONUNBUFFERED=1; python scripts/main.py "<URL>" --keep-temp

# Custom models
$env:PYTHONUNBUFFERED=1; python scripts/main.py "<URL>" --llm-model Qwen/Qwen3-32B --vlm-model Qwen/Qwen3-VL-8B-Instruct
```

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `MODELSCOPE_API_KEY` | (required) | ModelScope API key |
| `MODELSCOPE_API_BASE_URL` | api-inference.modelscope.cn/v1 | API endpoint |
| `VLM_MODEL` | Qwen/Qwen3-VL-8B-Instruct | Vision model for frame analysis |
| `LLM_MODEL` | moonshotai/Kimi-K2.5 | Primary LLM for segmentation & notes |
| `LLM_FALLBACK` | Qwen/Qwen3-235B-A22B,... | Comma-separated fallback LLMs |
| `VLM_FALLBACK` | (empty) | Fallback VL model |
| `ASR_MODEL` | base | faster-whisper model size |