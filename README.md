# Video-to-Notes-skill 🎥 → 📝

将B站、抖音视频 URL 一键转换为结构化的 Markdown 笔记，自动提取关键帧截图并生成图文并茂的文档。

## 功能特点

- **多平台支持** — Bilibili、抖音（Douyin）、本地视频文件
- **自动语音识别** — 基于 faster-whisper 的精准转录
- **智能分段** — LLM 自动将转录文本按话题切分为章节
- **关键帧提取** — 在章节锚点自动截取视频画面
- **视觉分析** — VLM（视觉语言模型）对截图进行分类和描述（保留 / 丢弃 / 提取文字）
- **笔记生成** — LLM 综合转录文本和视觉信息，生成图文并茂的笔记
- **自动清理** — 仅保留最终笔记和引用的截图，中间文件自动删除

## 前置条件

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/)（已安装并加入系统 PATH）
- [ModelScope](https://modelscope.cn) API Key（用于调用 LLM / VLM）

## 快速开始

### 1. 配置

将 `.env.example` 复制为 `.env`，填入 API Key：

```bash
cp .env.example .env
```

编辑 `.env`，至少设置 `MODELSCOPE_API_KEY`：

```
MODELSCOPE_API_KEY="你的-api-key"
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行

```bash
# Windows (PowerShell)
$env:PYTHONUNBUFFERED=1; python scripts/main.py "https://www.bilibili.com/video/BVxxxxxxxx"

# macOS / Linux
PYTHONUNBUFFERED=1 python scripts/main.py "https://www.bilibili.com/video/BVxxxxxxxx"
```

> `PYTHONUNBUFFERED=1` 是必需的，用于在终端中实时查看进度输出。

## 支持的视频来源

| 平台           | URL 示例                                      | 说明                                                                  |
| ------------ | ------------------------------------------- | ------------------------------------------------------------------- |
| **Bilibili** | `https://www.bilibili.com/video/BVxxxxxxxx` | 大部分视频直接可用。如遇 HTTP 412，需在 `Cookies/bilibili_cookies.json` 中放入 Cookie |
| **抖音**       | `https://v.douyin.com/xxxxx/`               | 无需 Cookie，基于 yt-dlp                                                 |
| **本地文件**     | `C:\videos\demo.mp4`                        | 支持 .mp4 / .flv / .mkv / .webm / .avi / .mov                         |

## 配置项

| 变量                        | 默认值                                                  | 说明                                                       |
| ------------------------- | ---------------------------------------------------- | -------------------------------------------------------- |
| `MODELSCOPE_API_KEY`      | —                                                    | **必填**。ModelScope API 密钥                                 |
| `MODELSCOPE_API_BASE_URL` | `https://api-inference.modelscope.cn/v1`             | API 端点                                                   |
| `VLM_MODEL`               | `Qwen/Qwen3-VL-8B-Instruct`                          | 视觉分析模型                                                   |
| `LLM_MODEL`               | `moonshotai/Kimi-K2.5`                               | 主 LLM（分段 & 笔记生成）                                         |
| `LLM_FALLBACK`            | `Qwen/Qwen3-235B-A22B,Qwen/Qwen3-32B,Qwen/Qwen3-14B` | 备用 LLM（逗号分隔，遇限流时按序降级）                                    |
| `VLM_FALLBACK`            | _(空)_                                                | 备用 VLM                                                   |
| `ASR_MODEL`               | `base`                                               | faster-whisper 模型规格：tiny / base / small / medium / large |

> LLM 框架会自动降级：当主模型遇到限流（rate limit）时，会按 `LLM_FALLBACK` 列表依次尝试，`Kimi-K2.5` → `Qwen3-235B` → `Qwen3-32B` → `Qwen3-14B`，确保高并发下仍能完成任务。

## 工作流程

```
视频 URL
   │
   ▼
┌─────────────┐
│  1. 下载视频  │  ← yt-dlp（Bilibili API / Douyin）
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  2. 语音转写  │  ← faster-whisper（ASR）
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  3. 智能分段  │  ← LLM 按话题切分转录文本
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  4. 帧截图    │  ← 在每个分段锚点截取关键帧
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  5. VLM 分析  │  ← 视觉模型识别并描述截图内容
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  6. 生成笔记  │  ← LLM 综合文字+图片输出 Markdown
└──────┬──────┘
       │
       ▼
   ✅ node.md + imgs/
```

## 命令行参数

| 参数                | 说明                    |
| ----------------- | --------------------- |
| `url`             | 视频 URL（位置参数，必填）       |
| `--skip-download` | 跳过下载（使用已存在的视频文件）      |
| `--skip-asr`      | 跳过语音识别（复用缓存的转录结果）     |
| `--skip-notes`    | 跳过笔记生成（仅截图和分析）        |
| `--api-key`       | 临时指定 API Key（覆盖 .env） |
| `--api-base`      | 临时指定 API 端点（覆盖 .env）  |
| `--vlm-model`     | 临时指定 VLM 模型           |
| `--llm-model`     | 临时指定 LLM 模型           |
| `--asr-model`     | ASR 模型规格（默认 base）     |
| `--keep-temp`     | 保留所有中间文件（视频、音频、未引用截图） |

### 使用示例

```bash
# 完整流程
$env:PYTHONUNBUFFERED=1; python scripts/main.py "https://www.bilibili.com/video/BV16zDfBtECQ"

# 跳过 ASR（复用已有转录）
$env:PYTHONUNBUFFERED=1; python scripts/main.py "https://v.douyin.com/EGqyDnirXU8/" --skip-asr

# 调试：保留中间文件
$env:PYTHONUNBUFFERED=1; python scripts/main.py "https://www.bilibili.com/video/BVxxxxxxxx" --keep-temp

# 自定义模型
$env:PYTHONUNBUFFERED=1; python scripts/main.py "https://www.bilibili.com/video/BVxxxxxxxx" --llm-model Qwen/Qwen3-32B --vlm-model Qwen/Qwen3-VL-8B-Instruct
```

## 输出结构

```
当前目录/
├── 视频名称/              ← 以视频标题命名的输出目录
│   ├── node.md            ← 最终笔记（Markdown）
│   └── imgs/              ← 笔记中引用的截图
│       ├── s01_a01_00_10.jpg
│       ├── s02_a03_01_25.jpg
│       └── ...
└── ...其他文件...           ← 中间文件默认自动删除
```

笔记默认输出到**当前工作目录**，以视频标题命名的文件夹中。

## 常见问题

### Bilibili 下载报 HTTP 412

Bilibili 对部分视频有反爬策略。请在 `Cookies/bilibili_cookies.json` 中放入你的浏览器 Cookie（从浏览器开发者工具中提取）。打开浏览器登录B站账号，按下F12,查看network,点击任意网络请求，找到Cookie，复制并交给你的Agent让它自行填写即可。
![Uploading 48033cca082afc158e73b998b6380804.png…]()

<br />

## 项目结构

```
video-to-notes/
├── .env.example           # 环境变量模板
├── SKILL.md               # 技能描述文件
├── requirements.txt       # Python 依赖
├── scripts/
│   ├── main.py            # 入口脚本
│   ├── core/
│   │   ├── pipeline.py    # 主流程编排
│   │   ├── transcriber.py # 语音识别（faster-whisper）
│   │   ├── segmenter.py   # 文本分段（LLM）
│   │   ├── anchor_builder.py  # 锚点计算 & 截图
│   │   ├── frame_collector.py # 帧采集
│   │   ├── frame_analyst.py   # VLM 视觉分析
│   │   └── note_writer.py     # 笔记生成
│   ├── platforms/
│   │   ├── base.py        # 平台基类
│   │   ├── bilibili.py    # Bilibili 下载
│   │   ├── douyin.py      # 抖音下载
│   │   └── local.py       # 本地文件读取
│   ├── prompts/
│   │   ├── segmenter.py       # 分段提示词
│   │   └── frame_classifier.py # 帧分类提示词
│   ├── models/
│   │   └── types.py       # 数据模型定义
│   └── utils/
│       ├── ffmpeg.py      # ffmpeg 工具封装
│       └── image.py       # 图片处理工具
├── Cookies/
│   └── bilibili_cookies.json  # Bilibili Cookie（可选）
└── README.md
```

