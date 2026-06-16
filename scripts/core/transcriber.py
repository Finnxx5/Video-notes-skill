import os, sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
from models.types import TranscriptSegment, WordTimestamp

# Windows: disable symlinks for huggingface_hub (requires admin/dev mode)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_LOCAL_FILES_ONLY", "0")

_whisper_model = None
_model_name = None

def _get_model(model_name="base", device="auto"):
    global _whisper_model, _model_name
    key = f"{model_name}_{device}"
    if _whisper_model is not None and _model_name == key:
        return _whisper_model
    
    # 1. 优先使用 faster-whisper（CTranslate2，CPU 上比 openai-whisper 快 4-8 倍）
    try:
        from faster_whisper import WhisperModel
        ct = "float16" if device == "cuda" else "int8"
        print(f"  [ASR] Loading faster-whisper model: {model_name}")
        _whisper_model = WhisperModel(model_name, device="cuda" if device == "cuda" else "cpu", compute_type=ct, num_workers=2)
        _model_name = key
        return _whisper_model
    except ImportError:
        pass
    except Exception as e:
        print(f"  [!] faster-whisper failed: {e}")

    # 2. 回退到 openai-whisper 本地模型
    local_model_path = _root.parent / "models" / f"{model_name}.pt"
    if local_model_path.exists():
        try:
            import whisper
            print(f"  [ASR] Loading local openai-whisper model: {local_model_path}")
            _whisper_model = whisper.load_model(str(local_model_path))
            _model_name = key
            return _whisper_model
        except Exception as e:
            print(f"  [!] Local model failed: {e}")

    # 3. 回退到 openai-whisper（从缓存或下载）
    try:
        import whisper
        _whisper_model = whisper.load_model(model_name)
        _model_name = key
        return _whisper_model
    except ImportError:
        raise RuntimeError("Install faster-whisper or openai-whisper: pip install faster-whisper")

def transcribe(video_path, model_name="base", language="zh", device="auto", progress_cb=None):
    model = _get_model(model_name, device)
    
    # faster-whisper 返回 (segments, info) 元组
    if hasattr(model, "transcribe") and not hasattr(model.__class__, "transcribe_file"):
        try:
            segs, info = model.transcribe(video_path, language=language, beam_size=5, word_timestamps=True)
            result = []
            for s in segs:
                words = [WordTimestamp(word=w.word, start=w.start, end=w.end, probability=w.probability) for w in (s.words or [])]
                result.append(TranscriptSegment(start=s.start, end=s.end, text=s.text.strip(), words=words))
        except (TypeError, ValueError):
            # openai-whisper 返回字典
            raw = model.transcribe(video_path, language=language, beam_size=5, word_timestamps=True)
            result = []
            for s in raw.get("segments", []):
                words = [WordTimestamp(word=w.get("word",""), start=w.get("start",0), end=w.get("end",0), probability=w.get("probability",0)) for w in s.get("words",[])]
                result.append(TranscriptSegment(start=s["start"], end=s["end"], text=s["text"].strip(), words=words))
    else:
        raw = model.transcribe(video_path, language=language, word_timestamps=True)
        result = []
        for s in raw.get("segments", []):
            words = [WordTimestamp(word=w.get("word",""), start=w.get("start",0), end=w.get("end",0), probability=w.get("probability",0)) for w in s.get("words",[])]
            result.append(TranscriptSegment(start=s["start"], end=s["end"], text=s["text"].strip(), words=words))
    
    full_text = " ".join(s.text for s in result)
    if progress_cb: progress_cb(100, f"ASR done: {len(result)} segs")
    return result, full_text

def format_transcript_timed(segments):
    lines = []
    for s in segments:
        mm, ss = int(s.start)//60, int(s.start)%60
        lines.append(f"[{mm:02d}:{ss:02d}] {s.text}")
    return "\n".join(lines)

def estimate_transcript_quality(segments):
    if not segments: return {"confidence":0,"usable":False,"segments_count":0}
    probs = [sum(w.probability for w in s.words)/max(len(s.words),1) for s in segments if s.words]
    avg = sum(probs)/len(probs) if probs else 0
    return {"confidence":round(avg,3),"usable":avg>0.5,"segments_count":len(segments),"duration":sum(s.end-s.start for s in segments)}
