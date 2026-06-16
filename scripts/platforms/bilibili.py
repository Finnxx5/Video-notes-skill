import os, re, json, shutil, sys, time as _time
from pathlib import Path
from typing import Optional
from .base import BaseDownloader
import urllib.request, urllib.error
from http.cookiejar import MozillaCookieJar

_MAIN = Path(__file__).resolve().parent.parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
HD = {"User-Agent": UA, "Referer": "https://www.bilibili.com/", "Origin": "https://www.bilibili.com"}

# Global cookie jar
_COOKIE_JAR = None

def _init_cookies(cookie_path=None):
    global _COOKIE_JAR
    if _COOKIE_JAR is not None:
        return _COOKIE_JAR
    
    cp = Path(cookie_path) if cookie_path else (_MAIN / "Cookies" / "bilibili_cookies.json")
    if not cp.exists() or cp.stat().st_size <= 10:
        return _COOKIE_JAR  # no cookies, return None

    # Try JSON format: {"name": "value", ...}
    try:
        from http.cookiejar import Cookie
        import time
        ck = json.loads(cp.read_text("utf-8"))
        _COOKIE_JAR = MozillaCookieJar()
        for k, v in ck.items():
            if k and v and str(v).strip():
                c = Cookie(
                    version=0, name=k, value=str(v),
                    port=None, port_specified=False,
                    domain=".bilibili.com", domain_specified=True, domain_initial_dot=True,
                    path="/", path_specified=True,
                    secure=False, expires=None, discard=True,
                    comment=None, comment_url=None,
                    rest={},
                    rfc2109=False,
                )
                _COOKIE_JAR.set_cookie(c)
        print(f"  [Cookie] Loaded {len(ck)} entries from {cp.name}")
    except Exception as e:
        print(f"  [Cookie] Failed to load {cp}: {e}")
        _COOKIE_JAR = None
    return _COOKIE_JAR


def _api(path, timeout=15, use_cookies=True):
    """Call Bilibili API. Returns JSON dict on success, raises on failure."""
    req = urllib.request.Request(f"https://api.bilibili.com{path}", headers=HD)
    if use_cookies and _COOKIE_JAR:
        try:
            _COOKIE_JAR.add_cookie_header(req)
        except:
            pass
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # Retry once without cookie to debug
        raise RuntimeError(f"Bilibili API {e.code}: {path}")

def _netscape_cookies(cookie_path):
    ck = json.loads(cookie_path.read_text("utf-8"))
    import tempfile
    t = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    t.write("# Netscape HTTP Cookie File\n")
    for k, v in ck.items():
        if k and v and k.strip():
            t.write(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{k}\t{v}\n")
    t.close()
    return t.name

def _download_url(audio_url, out_path, timeout=120):
    req = urllib.request.Request(audio_url, headers=HD)
    if _COOKIE_JAR:
        try:
            _COOKIE_JAR.add_cookie_header(req)
        except:
            pass
    with urllib.request.urlopen(req, timeout=timeout) as r:
        with open(out_path, "wb") as f:
            while True:
                chunk = r.read(512 * 1024)
                if not chunk: break
                f.write(chunk)
    return Path(out_path).stat().st_size

class BilibiliDownloader(BaseDownloader):
    def __init__(self, output_dir, cookie_path=None):
        super().__init__(output_dir)
        self.cookie_path = cookie_path or (_MAIN / "Cookies" / "bilibili_cookies.json")
        _init_cookies(self.cookie_path)

    async def download(self, url):
        bv = re.search(r'BV[a-zA-Z0-9]+', url)
        if not bv: return None, "", ""
        bv = bv.group(0)

        # Try API first
        info = None
        try:
            info = _api(f"/x/web-interface/view?bvid={bv}")
        except Exception as e:
            err_msg = str(e)
            if "412" in err_msg:
                print(f"  [!] Bilibili API blocked (412). Auto-falling back to yt-dlp.")
                print(f"  [!] If this fails, put cookies in: {self.cookie_path}")
            else:
                print(f"  [!] API error: {err_msg}")

        cid = None
        title = None
        safe = None

        if info and info.get("code") == 0:
            cid = info["data"]["cid"]
            title = info["data"]["title"]
            safe = self.safe_name(title) or f"BV_{bv}"
            print(f"  Video: {title}")
        else:
            # Fallback: use yt-dlp directly (without API)
            safe = f"BV_{bv}"
            d = self.output_dir / safe
            d.mkdir(parents=True, exist_ok=True)
            vp = str(d / f"{safe}.mp4")
            result = await self._download_via_ytdlp(f"https://www.bilibili.com/video/{bv}", vp)
            if result:
                print(f"  Downloaded via yt-dlp (no API)")
            return result, safe, None

        sub_path = await self._fetch_subtitles(bv, cid, safe)
        vid_path = await self._download_via_api(cid, bv, safe)
        return vid_path, safe, sub_path

    async def _fetch_subtitles(self, bv, cid, safe):
        d = self.output_dir / safe
        try: os.makedirs(str(d), exist_ok=True)
        except: pass
        sub_url = None
        for api_path in [f"/x/player/v2?cid={cid}&bvid={bv}", f"/x/player/wbi/v2?cid={cid}&bvid={bv}"]:
            try:
                r = _api(api_path)
                ss = r.get("data", {}).get("subtitle", {}).get("subtitles", [])
                if ss: sub_url = ss[0].get("subtitle_url", ""); break
            except: pass
        if not sub_url:
            print("  No B绔?subtitles, will use ASR")
            return None
        if sub_url.startswith("//"): sub_url = "https:" + sub_url
        try:
            sj = json.loads(urllib.request.urlopen(urllib.request.Request(sub_url, headers=HD)).read())
            lines = [{"start": it["from"], "text": it["content"]} for it in sj.get("body", [])]
            tp = d / f"{safe}_sub.txt"
            with open(tp, "w", encoding="utf-8") as f:
                for ln in lines:
                    mm, ss = int(ln["start"] // 60), int(ln["start"] % 60)
                    f.write(f"[{mm:02d}:{ss:02d}] {ln['text']}\n")
            print(f"  Subtitles: {len(lines)} lines")
            return str(tp)
        except Exception as e:
            print(f"  Subtitle fail: {e}")
            return None

    async def _download_via_api(self, cid, bv, safe):
        d = self.output_dir / safe
        try: os.makedirs(str(d), exist_ok=True)
        except: pass
        vp = str(d / f"{safe}.mp4")
        ap = str(d / f"{safe}_audio.m4a")

        # Get DASH URLs from API
        play = None
        try:
            play = _api(f"/x/player/playurl?cid={cid}&bvid={bv}&qn=64&fnval=4048&fourk=1")
        except Exception as e:
            print(f"  PlayURL API fail: {e}")

        videos = play.get("data", {}).get("dash", {}).get("video", []) if play else []
        audios = play.get("data", {}).get("dash", {}).get("audio", []) if play else []
        if videos:
            print(f"  DASH: {len(videos)} video streams, {len(audios)} audio streams")

        # --- Download video ---
        if not (Path(vp).exists() and Path(vp).stat().st_size > 1024):
            if not videos:
                return await self._download_via_ytdlp(f"https://www.bilibili.com/video/{bv}", vp)

            # Pick best video (prefer <=720p)
            best_v = videos[0]
            for v in videos:
                if v.get("height", 0) <= 720:
                    best_v = v; break
            video_urls = [best_v.get("base_url") or best_v.get("url", "")]
            for v in videos:
                u = v.get("base_url") or v.get("url", "")
                if u and u not in video_urls: video_urls.append(u)

            print(f"  Video: {best_v.get('width','?')}x{best_v.get('height','?')} {best_v.get('frame_rate','?')}fps")
            for vu in video_urls:
                if vu.startswith("//"): vu = "https:" + vu
                try:
                    size = _download_url(vu, vp, timeout=180)
                    if size > 1024:
                        print(f"  Downloaded: {vp} ({size/1024/1024:.1f}MB)")
                        break
                except Exception as e:
                    err_str = str(e)[:120]
                    print(f"  CDN fail ({vu[-40:]}): {err_str}")
                    _time.sleep(1)
            else:
                print("  All video CDNs failed, trying yt-dlp")
                return await self._download_via_ytdlp(f"https://www.bilibili.com/video/{bv}", vp)
        else:
            print(f"  Reusing: {vp}")

        # --- Download audio (always try, video-only MP4 has no audio track) ---
        if not (Path(ap).exists() and Path(ap).stat().st_size > 500000):
            if audios:
                audio_urls = [a.get("base_url") or a.get("url", "") for a in audios if a.get("base_url") or a.get("url")]
                for au in audio_urls:
                    if au.startswith("//"): au = "https:" + au
                    try:
                        size = _download_url(au, ap, timeout=120)
                        if size > 500000:
                            print(f"  Audio: {ap} ({size/1024:.0f}KB)")
                            break
                    except Exception as e:
                        _time.sleep(1)
            else:
                print("  No audio streams in DASH")

        return vp

    async def _download_via_ytdlp(self, url, vp):
        try:
            import yt_dlp
        except ImportError:
            print("  yt-dlp not installed")
            return None

        d = Path(vp).parent
        opts = {
            "outtmpl": str(d / "%(id)s.%(ext)s"),
            "noplaylist": True, "quiet": True,
            "retries": 10, "fragment_retries": 10,
            "force_ipv4": True,
            "format": "bestvideo[height<=720]/best",
            "sleep_requests": 0.5,
            "extractor_retries": 5,
        }

        for p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(p, None)

        if self.cookie_path.exists():
            try:
                opts["cookiefile"] = _netscape_cookies(self.cookie_path)
            except Exception as e:
                print(f"  Cookie error: {e}")

        for attempt in range(3):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                for ext in ("*.mp4", "*.flv", "*.mkv", "*.webm"):
                    cs = sorted(Path(d).glob(ext), key=lambda p: p.stat().st_mtime, reverse=True)
                    for c in cs:
                        if str(c) != vp:
                            shutil.move(str(c), vp)
                            print(f"  Downloaded (yt-dlp): {vp}")
                            return vp
                if Path(vp).exists(): return vp
                break
            except Exception as e:
                print(f"  yt-dlp attempt {attempt+1}/3: {e}")
                _time.sleep(2 ** attempt)
        return None


