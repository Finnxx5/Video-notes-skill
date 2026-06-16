# coding: utf-8
"""Video-to-Notes Skill - Convert video URL to structured Markdown notes."""

# Disable bytecode cache to avoid sandbox permission issues
import os
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import sys, argparse, asyncio, shutil
from pathlib import Path

# Skill root = parent of scripts/
SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

# HuggingFace mirror for China (faster-whisper model download)
if not os.getenv("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Load .env from skill root
try:
    from dotenv import load_dotenv
    env_file = SKILL_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"  [Env] Loaded: {env_file}")
    else:
        print(f"  [!] No .env found at {env_file}")
        print(f"  [!] Copy .env.example to .env and fill in your API keys")
except ImportError:
    pass

from core.pipeline import run_pipeline


def parse_args():
    p = argparse.ArgumentParser(description="Video-to-Notes: Convert video URL to Markdown notes")
    p.add_argument("url", nargs="?", default=None, help="Video URL (Bilibili, Douyin, or local file)")
    p.add_argument("--skip-download", action="store_true")
    p.add_argument("--skip-asr", action="store_true")
    p.add_argument("--skip-notes", action="store_true")
    p.add_argument("--api-key")
    p.add_argument("--api-base")
    p.add_argument("--vlm-model")
    p.add_argument("--llm-model")
    p.add_argument("--asr-model", default="base")
    p.add_argument("--keep-temp", action="store_true", help="Keep intermediate files (video, frames, audio)")
    return p.parse_args()


def cleanup(output_dir, keep_temp):
    """Remove intermediate files, keep only node.md and images it references."""
    if keep_temp:
        return
    od = Path(output_dir)
    if not od.exists():
        return

    # Parse node.md to find referenced images
    note_path = od / "node.md"
    referenced_images = set()
    if note_path.exists():
        import re
        for m in re.finditer(r'!\[.*?\]\(imgs/([^)]+)\)', note_path.read_text("utf-8")):
            referenced_images.add(m.group(1))

    removed = 0
    for item in od.iterdir():
        name = item.name.lower()
        # Always keep node.md
        if name == "node.md":
            continue
        # Keep imgs/ dir with only referenced images
        if item.is_dir() and name == "imgs":
            for frame_file in list(item.iterdir()):
                if frame_file.name not in referenced_images:
                    try:
                        frame_file.unlink()
                        removed += 1
                    except:
                        pass
            # Remove imgs/ dir if empty
            if not list(item.iterdir()):
                try:
                    item.rmdir()
                except:
                    pass
        # Keep referenced images at root level too
        elif item.suffix.lower() in (".jpg", ".png") and item.name in referenced_images:
            continue
        # Delete everything else (video, audio, txt, unreferenced images)
        elif item.is_dir():
            try:
                shutil.rmtree(str(item), ignore_errors=True)
                removed += 1
            except:
                pass
        elif item.suffix.lower() in (".mp4", ".flv", ".mkv", ".webm", ".m4a", ".wav", ".jpg", ".png", ".txt"):
            try:
                item.unlink()
                removed += 1
            except:
                pass

    if removed:
        ref_count = len(referenced_images)
        print(f"\n  [Cleanup] Removed {removed} intermediate files, kept node.md + imgs/ ({ref_count} image(s))")


def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except:
            pass

    args = parse_args()
    url = args.url or os.getenv("DEFAULT_VIDEO_URL", "")
    if not url:
        print("Usage: python scripts/main.py <URL>")
        print("First copy .env.example to .env and fill in your API keys.")
        return 1

    api_key = args.api_key or os.getenv("MODELSCOPE_API_KEY") or os.getenv("API_KEY")
    api_base = args.api_base or os.getenv("MODELSCOPE_API_BASE_URL", "https://api-inference.modelscope.cn/v1")
    vlm = args.vlm_model or os.getenv("VLM_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
    llm = args.llm_model or os.getenv("LLM_MODEL", "moonshotai/Kimi-K2.5")
    llm_fallback = [m.strip() for m in os.getenv("LLM_FALLBACK", "").split(",") if m.strip()]
    vlm_fallback = os.getenv("VLM_FALLBACK", "")

    if not api_key:
        print("Error: No API key. Set MODELSCOPE_API_KEY in .env")
        return 1

    # Output goes to CWD (caller's directory) — guaranteed not to be the skill dir
    output_base = os.getcwd()

    print("=" * 60)
    print(f"URL: {url}")
    print(f"ASR: {args.asr_model}  VLM: {vlm}  LLM: {llm}")
    print("=" * 60)

    result = asyncio.run(run_pipeline(
        video_url=url,
        api_key=api_key,
        base_url=api_base,
        vlm_model=vlm,
        llm_model=llm,
        llm_fallback=llm_fallback,
        vlm_fallback=vlm_fallback,
        asr_model=args.asr_model,
        output_base=output_base,
        skip_download=args.skip_download,
        skip_asr=args.skip_asr,
        skip_notes=args.skip_notes,
    ))

    print("\n" + "=" * 60)
    if result.success:
        print("OK")
        if result.note_path:
            print(f"Note: {result.note_path}")
        for k, v in result.stats.items():
            print(f"  {k}: {v}")

        # Cleanup intermediate files
        if result.output_dir:
            try:
                cleanup(str(result.output_dir), args.keep_temp)
            except Exception:
                pass  # sandbox may block some file operations
    else:
        print(f"FAIL: {result.error}")
    print("=" * 60)
    return 0 if result.success else 1


if __name__ == "__main__":
    main()