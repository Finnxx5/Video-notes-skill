from typing import Optional
import re
from pathlib import Path
class BaseDownloader:
    def __init__(self,output_dir): self.output_dir=Path(output_dir)
    async def download(self,url): raise NotImplementedError
    @staticmethod
    def safe_name(name, maxlen=50):
        # Remove or replace characters unsafe for filesystem/dirs (keep ASCII alphanumeric, underscore, hyphen, space)
        name = re.sub(r'[<>:"/|?*]', "_", name)
        name = re.sub(r'[^\x00-\x7F]', "", name)  # strip non-ASCII (Chinese, etc.)
        name = re.sub(r'[+&,%$#@!~`\'=()\[\]{}]', "_", name)  # strip special chars
        name = re.sub(r'\s+', "_", name).strip("._ ")
        return name[:maxlen].strip() or "video"
def detect(url):
    if not url or not url.strip(): return None
    url=url.strip()
    p=Path(url)
    if p.exists() and p.suffix.lower() in(".mp4",".flv",".mkv",".webm",".avi",".mov",".ts"): return "local"
    if re.search(r'BV[a-zA-Z0-9]+',url) or "bilibili.com" in url: return "bilibili"
    if "douyin.com" in url: return "douyin"
    return None