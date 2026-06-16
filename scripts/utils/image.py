import base64
from pathlib import Path
def encode_base64(image_path):
    with open(image_path,"rb") as f: data=f.read()
    ext=Path(image_path).suffix.lower().lstrip(".")
    mime="jpeg" if ext in ("jpg","jpeg") else ext
    return f"data:image/{mime};base64,{base64.b64encode(data).decode()}"
