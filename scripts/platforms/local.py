from pathlib import Path
from .base import BaseDownloader
class LocalDownloader(BaseDownloader):
    async def download(self,url):
        p=Path(url).resolve()
        if not p.exists(): return None,"","not found"
        return str(p),self.safe_name(p.stem),None
