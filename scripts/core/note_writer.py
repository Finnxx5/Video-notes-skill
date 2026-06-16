import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))

NOTE_SYSTEM = {
    "tutorial": "你正在撰写一篇教程笔记。输入中的<transcript>和<visual_observations>是原始素材——必须内化后用自己的话重写，禁止逐句复制。用简体中文输出。用![时间](imgs/xxx.jpg)插入截图。\n最后必须添加一个「总结」章节（## 总结），提炼视频的核心思想、关键观点和主要内容，帮助读者快速回顾全篇。",
    "news": "你正在撰写一篇新闻摘要。输入中的<transcript>和<visual_observations>是原始素材——必须内化为自己的分析。用表格展示数据，用引用块展示引语。用简体中文输出。用![时间](imgs/xxx.jpg)插入截图。\n最后必须添加一个「总结」章节（## 总结），提炼视频的核心观点和关键信息。",
    "lecture": "你正在撰写学习笔记。输入中的<transcript>和<visual_observations>是原始素材——必须用自己的话重写。首次出现的术语需定义。用层级列表组织概念。用简体中文输出。用![时间](imgs/xxx.jpg)插入截图。\n最后必须添加一个「总结」章节（## 总结），提炼视频的核心知识点和要点。",
}

async def generate_note(analysis, api_key, base_url, llm_model="moonshotai/Kimi-K2.5", fallback=""):
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    sys_prompt = NOTE_SYSTEM.get(analysis.video_type, NOTE_SYSTEM["tutorial"])
    user_prompt = _build_prompt(analysis)
    fb_list = fallback if isinstance(fallback, list) else ([fallback] if fallback else [])
    models_to_try = [llm_model] + [m for m in fb_list if m and m != llm_model]
    for m in models_to_try:
        try:
            resp = await client.chat.completions.create(model=m, messages=[{"role":"system","content":sys_prompt},{"role":"user","content":user_prompt}], max_tokens=16384, temperature=0.3)
            note = resp.choices[0].message.content
            return note
        except Exception as e:
            if m == models_to_try[-1]:
                print(f"Note generation failed: {e}, using fallback")
                return _fallback_note(analysis)
            print(f"  LLM {m} failed: {e}, trying fallback...")
    return _fallback_note(analysis)


def _build_prompt(analysis):
    parts = [f"# {analysis.title}\n\n## Transcript\n"]
    for seg in analysis.segments:
        parts.append(f"\n### {seg.id}. {seg.title} ({_fmt(seg.start)}-{_fmt(seg.end)})\n{seg.summary}")
        if seg.transcript_text:
            parts.append(f"\n<transcript>\n{seg.transcript_text}\n</transcript>")

        # Collect visual snapshots as context (not standalone blocks)
        c_snapshots = []
        c_images = []
        b_texts = []
        for f in seg.frames:
            name = Path(f.path).name if f.path else ""
            if f.classification == "B" and f.extracted_text:
                b_texts.append(f.extracted_text.strip())
            elif f.classification == "C":
                desc = f.description or ""
                snap = f"At {f.time_str}: {desc.strip()}" if desc.strip() else ""
                if snap:
                    c_snapshots.append(snap)
                # Track image for bottom-of-segment listing
                c_images.append(f"![{f.time_str}](imgs/{name})")

        if b_texts:
            parts.append("\n<extracted_content>\n" + "\n---\n".join(b_texts) + "\n</extracted_content>")
        if c_snapshots:
            parts.append("\n<visual_observations>\n" + "\n".join(c_snapshots) + "\n</visual_observations>")
        if c_images:
            parts.append("\n<available_screenshots>\n" + "\n".join(c_images) + "\n</available_screenshots>")

    parts.append("\n\n---\n**Instructions:**\n")
    parts.append("1. Rewrite ALL content in your own words. Never copy-paste any sentence from <visual_observations> or <transcript> verbatim.\n")
    parts.append("2. Synthesize visual observations into your narrative - mention what's shown, don't quote.\n")
    parts.append("3. Include screenshots using: ![time](imgs/xxx.jpg) - place after the relevant paragraph.\n")
    parts.append("4. Keep the same level of detail as the source material.\n")
    parts.append("5. **必须**在笔记末尾添加一个「总结」章节（## 总结），用 3-5 个要点或一段连贯的文字，概括视频的核心思想、关键观点和主要内容。")
    return "\n".join(parts)

def _fallback_note(analysis):
    lines = [f"# {analysis.title}\n"]
    for seg in analysis.segments:
        lines.append(f"## {seg.title}")
        lines.append(seg.summary + "\n")
        for f in seg.frames:
            if f.classification=="C" and f.path:
                name = Path(f.path).name
                lines.append(f"![{f.time_str}](imgs/{name})\n")
    return "\n".join(lines)

def _fmt(s): mm,ss=int(s)//60,int(s)%60; return f"{mm:02d}:{ss:02d}"
