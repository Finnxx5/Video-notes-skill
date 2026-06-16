import os, sys, re, time as _time, shutil, uuid
from pathlib import Path
from typing import Optional
from .base import BaseDownloader

def _ensure_dir(path):
    import time
    d = Path(path)
    for _ in range(3):
        try:
            d.mkdir(parents=True, exist_ok=True)
            if d.exists():
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise FileNotFoundError(f'Cannot create directory: {d}')

class DouyinDownloader(BaseDownloader):
    def __init__(self, output_dir, cookie_path=None):
        super().__init__(output_dir)

    async def download(self, url):
        try:
            import yt_dlp
        except ImportError:
            return None, "", "yt-dlp not installed"

        for p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(p, None)

        # Step 1: Get video info (no download)
        ydl_opts = {
            "quiet": True, "noplaylist": True, "force_ipv4": True,
            "extractor_retries": 5, "socket_timeout": 30,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            return None, "", f"extract info failed: {e}"

        title = info.get("title", "douyin_video")
        safe = self.safe_name(title)
        od = self.output_dir / safe
        target = od / "video.mp4"

        # Already downloaded?
        if target.exists() and target.stat().st_size > 1024:
            print(f"  Video: {title}")
            print(f"  Reusing: {target}")
            return str(target), safe, None

        # Step 2: Create target dir
        _ensure_dir(od)

        print(f"  Video: {title}")

        # Step 3: Download to temp short path
        tmp_name = f"_dy_{uuid.uuid4().hex[:8]}.mp4"
        tmp_path = self.output_dir / tmp_name

        dl_opts = {
            "outtmpl": str(tmp_path.absolute()),
            "noplaylist": True, "quiet": True,
            "retries": 10, "fragment_retries": 10,
            "force_ipv4": True,
            "format": "best[height<=720]/best",
            "extractor_retries": 5, "socket_timeout": 30,
        }

        for attempt in range(3):
            try:
                with yt_dlp.YoutubeDL(dl_opts) as ydl:
                    ydl.download([url])

                # Find downloaded file
                found = None
                if tmp_path.exists() and tmp_path.stat().st_size > 1024:
                    found = tmp_path

                if not found:
                    for f in self.output_dir.rglob("*"):
                        if f.is_file() and f.suffix in (".mp4", ".flv", ".mkv", ".webm"):
                            if f.stat().st_size > 1024 and "audio" not in f.name.lower():
                                found = f
                                break

                if found:
                    _move_file(found, target)
                    if target.exists() and target.stat().st_size > 1024:
                        print(f"  Downloaded: {target}")
                        _cleanup_dirs(self.output_dir, od)
                        return str(target), safe, None

                print(f"  Attempt {attempt+1}/3: no file")
                if attempt < 2:
                    _time.sleep(2 ** attempt)

            except Exception as e:
                print(f"  Attempt {attempt+1}/3: {e}")
                if attempt < 2:
                    _time.sleep(2 ** attempt)

        return None, "", "download failed"


def _move_file(src, dst):
    """Move file, handling long paths on Windows."""
    try:
        shutil.move(str(src), str(dst))
    except Exception:
        try:
            import shutil as _sh
            _sh.copy2(str(src), str(dst))
            try:
                src.unlink()
            except:
                pass
        except Exception:
            # Last resort: read/write binary
            with open(src, "rb") as fsrc:
                with open(dst, "wb") as fdst:
                    while True:
                        chunk = fsrc.read(8192)
                        if not chunk:
                            break
                        fdst.write(chunk)
            try:
                src.unlink()
            except:
                pass


def _cleanup_dirs(output_dir, keep_dir):
    """Remove leftover yt-dlp temp directories."""
    for d in output_dir.iterdir():
        if d.is_dir() and d != keep_dir:
            name = d.name
            if "..#" in name or name.startswith("_dy_") or name.startswith("_dl_"):
                try:
                    shutil.rmtree(str(d), ignore_errors=True)
                except:
                    pass