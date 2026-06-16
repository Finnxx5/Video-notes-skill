import subprocess, os
from pathlib import Path
CF = subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0
def capture_frame(video_path, time_seconds, output_path, quality=2):
    if not Path(video_path).exists(): return False
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    r=subprocess.run(["ffmpeg","-ss",str(time_seconds),"-i",video_path,"-frames:v","1","-q:v",str(quality),output_path,"-y"],capture_output=True,timeout=15,creationflags=CF)
    return r.returncode==0 and Path(output_path).exists()
