---
title: YT Automation Bot
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
license: mit
app_port: 7860
---

<div align="center">

# 🎬 YT Shorts Automation Bot

**End-to-End AI-Powered YouTube Shorts Pipeline for Civil Engineering Content**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](#-docker-deployment)
[![Hugging Face Spaces](https://img.shields.io/badge/%F0%9F%A4%97-Spaces-yellow)](https://huggingface.co/spaces)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot%20API-26A5E4?logo=telegram&logoColor=white)](#-telegram-bot-commands)

---

A production-grade, fully autonomous pipeline that **scripts → voices → edits → subtitles → uploads** bilingual YouTube Shorts — all controlled from a single Telegram bot. Built for the civil engineering & home construction niche with native Tamil language support.

[Features](#-features) · [Architecture](#-architecture) · [Getting Started](#-getting-started) · [Usage](#-usage) · [Deployment](#-docker-deployment) · [License](#-license)

</div>

---

## 🌟 Features

### AI Content Generation
- **Gemini-Powered Scripting** — Generates high-retention scripts covering structural planning, material selection (M-Sand vs. river sand, bricks vs. blocks), Vastu-compliant architecture, and region-specific construction tips for Tamil Nadu.
- **5-Model Fallback Chain** — Automatic model rotation (`gemini-2.5-flash` → `gemini-2.0-flash` → `gemini-2.5-flash-preview` → `gemini-2.0-flash-lite` → `gemini-2.5-pro`) with multi-key support to eliminate quota exhaustion (`429`) and service unavailability (`503`) errors.
- **Google Search Grounding** — Optionally grounds generated content with real-time search results for factual accuracy.

### Text-to-Speech & Audio
- **Gemini TTS** — Primary narration via `gemini-3.1-flash-tts-preview` with automatic fallback to `gemini-2.5-flash-preview-tts` and `gTTS` for zero-downtime audio generation.
- **Scene-Synced Audio** — Generates per-scene narration segments and concatenates them for precise audio-visual timing alignment.

### Visual Acquisition & Video Rendering
- **Multi-Source Asset Pipeline** — Three interchangeable visual backends:
  | Source | Description |
  |--------|-------------|
  | `youtube` | Creative Commons clips via `yt-dlp` with dynamic search indexing |
  | `pexels` / `pixabay` | Professional stock footage from curated APIs |
  | `ai` | AI-generated video via Wan 2.1 on Hugging Face Spaces |
- **Zero-Repeat Guarantee** — Unique clip selection per scene using dynamic search indexing (`ytsearch1`, `ytsearch2`, ...) and staggered time offsets. Previously used clips are tracked for 30 days.
- **HD Vertical Rendering** — FFmpeg pipeline standardizes all footage to **1080×1920** with center-crop, watermark overlay, and H.264 encoding at CRF 23 (`high` profile, level `4.1` with B-frames).
- **Motion Graphics Engine** — Pillow-based animation renderer for data visualizations, comparison cards, and overlay graphics with Tamil/Latin font auto-detection.

### Bilingual Subtitles & Captions
- **Groq Whisper Transcription** — Tamil audio → English closed captions (`.srt`) in ~4 seconds via the Groq Whisper API, with Gemini audio-upload as fallback.
- **Stylized ASS Subtitles** — SRT captions converted to Advanced SubStation Alpha format with custom styling (`Nirmala UI`, bold outlines, yellow accents, safe-zone margins).
- **Flexible Modes** — Toggle between `baked` (hardcoded into video) and `cc` (uploaded as separate closed caption track).

### SEO & Organic Reach Optimization
- **Bilingual Double-Indexing** — Titles combine Tamil and English (e.g., *"வீடு கட்டும் தவறு | Avoid This Building Mistake"*) for maximum search coverage.
- **Language Metadata Injection** — Sets `defaultLanguage` and `defaultAudioLanguage` to `ta` (Tamil) for algorithm-optimized feed targeting.
- **Multilingual Localizations** — Auto-uploads translated metadata (Hindi, Spanish, Tamil) via the YouTube Localizations API.
- **Strategic Hashtags** — `#Shorts` + top 3 niche keywords placed at the description start for clickable blue link visibility.
- **Trending Topic Integration** — Real-time trend scraping from YouTube autocomplete, Google Trends RSS, and rotating daily viral hashtag sets.
- **CTR-Optimized Thumbnails** — Auto-extracted hook frame at `3.0s` with large, capitalized text overlay (`120px` bold Arial) for mobile discovery.

### Telegram Bot Control Center
- **Interactive Commands** — Full pipeline orchestration from your phone:
  | Command | Description |
  |---------|-------------|
  | `/generate` | Trigger immediate video generation with live stage progress |
  | `/status` | Check recent job status and failure diagnostics |
  | `/schedule` | Set daily posting times in IST (Indian Standard Time) |
  | `/view_schedule` | View all active posting timelines |
  | `/clearschedule` | Wipe all active schedulers |
  | `/autopost` | Toggle auto-approval mode (skip manual review) |
  | `/cancel` | Cancel the current running process |
- **Approval Workflow** — Preview generated video + script in Telegram before publishing, or enable auto-post for hands-free operation.
- **Multi-User Security** — Whitelist-based access via comma-separated `TELEGRAM_CHAT_ID`.

---

## 🏗 Architecture

```mermaid
flowchart LR
    subgraph Control["🤖 Control Layer"]
        TG[Telegram Bot]
        SCHED[APScheduler<br/>IST Cron Jobs]
        API[FastAPI<br/>Health Check]
    end

    subgraph Core["⚙️ Core"]
        ORCH[Orchestrator]
        DB[(PostgreSQL<br/>Jobs · Schedules · Assets)]
    end

    subgraph Engines["🔧 Engine Layer"]
        SE[Script Engine<br/>Gemini 5-Model Chain]
        AE[Audio Engine<br/>Gemini TTS + gTTS]
        VE[Video Engine<br/>FFmpeg + yt-dlp]
        AIVE[AI Video Engine<br/>Wan 2.1 · HF Spaces]
        ANI[Animation Engine<br/>Pillow Renderer]
        TE[Trends Engine<br/>YT Autocomplete · Trends RSS]
        YE[YouTube Engine<br/>OAuth Upload + SEO]
    end

    TG --> ORCH
    SCHED --> ORCH
    ORCH --> DB
    ORCH --> SE --> AE --> VE --> YE
    VE --> AIVE
    VE --> ANI
    SE --> TE
    API -.->|":7860"| TG
```

### Pipeline Lifecycle

```
SCHEDULED → GENERATING_SCRIPT → GENERATING_AUDIO → GENERATING_VISUALS
     → RENDERING_DRAFT → AWAITING_APPROVAL → UPLOADING → UPLOADED
```

Each stage is tracked in the database with failure diagnostics. Failed jobs capture the error stage, human-readable message, and full stack trace for debugging.

---

## 🚀 Getting Started

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Required |
| FFmpeg & FFprobe | Latest | Must be on system `PATH` |
| PostgreSQL | 15+ | Or use the Docker Compose stack |
| yt-dlp | Latest | `pip install yt-dlp` |

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/Vinoth-46/YT-Automation.git
cd YT-Automation

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
# ─── AI & Content APIs ────────────────────────────────────────
GEMINI_API_KEY=key_1,key_2,key_3          # Comma-separated for rotation
OPENROUTER_API_KEY=your_openrouter_key
GROQ_API_KEY=your_groq_key
HF_TOKEN=your_huggingface_token           # For Wan 2.1 AI video

# ─── Stock Footage APIs ───────────────────────────────────────
PEXELS_API_KEY=your_pexels_key
PIXABAY_API_KEY=your_pixabay_key

# ─── Telegram ─────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=user_id_1,user_id_2      # Whitelisted user IDs

# ─── Database ─────────────────────────────────────────────────
POSTGRES_URL=postgresql+asyncpg://user:password@localhost:5432/yt_automation

# ─── Engine Configuration ─────────────────────────────────────
SUBTITLE_MODE=baked                        # 'baked' or 'cc'
VIDEO_SOURCE=youtube                       # 'youtube', 'pexels', or 'ai'
```

### Database Setup

```bash
# Option A: Using Docker Compose (recommended)
docker compose up -d db

# Option B: Manual initialization
python -c "import asyncio; from core.database import init_db; asyncio.run(init_db())"
```

---

## 📖 Usage

### Start the Telegram Bot

```bash
python -m bot.main
```

The bot starts alongside a FastAPI health-check server on port `7860`. Open Telegram, send `/start` to your bot, and use `/generate` to create your first video.

### Run a Direct Pipeline Test

```bash
python scratch/test_generate_youtube.py
```

Bypasses the Telegram interface and runs the full pipeline (script → audio → video → thumbnail) directly in the terminal.

---

## 🐳 Docker Deployment

### Using Docker Compose (Full Stack)

```bash
# Start PostgreSQL + Bot
docker compose up -d

# View logs
docker compose logs -f bot
```

### Standalone Docker Build

```bash
docker build -t yt-automation .
docker run -d \
  --env-file .env \
  -p 7860:7860 \
  -v ./outputs:/app/outputs \
  -v ./credentials:/app/credentials \
  yt-automation
```

### Hugging Face Spaces

This project includes a `Dockerfile` pre-configured for [Hugging Face Spaces](https://huggingface.co/spaces) deployment. Set your environment variables as Space secrets and deploy directly from the repository.

---

## 📂 Project Structure

```
YT-Automation/
├── bot/                          # Telegram Bot Interface
│   ├── main.py                   # Bot initialization, FastAPI server, lifecycle management
│   └── handlers.py               # Command handlers, inline keyboards, approval workflow
│
├── core/                         # Core Application Layer
│   ├── config.py                 # Pydantic settings, path resolution, environment loading
│   ├── database.py               # Async SQLAlchemy session management
│   ├── models.py                 # ORM models (Job, Schedule, User, Channel, Assets)
│   ├── orchestrator.py           # Pipeline lifecycle: script → audio → video → upload
│   ├── scheduler.py              # APScheduler service with IST cron job management
│   └── security.py               # Logging security filters (token redaction)
│
├── engines/                      # Processing Engines
│   ├── script_engine.py          # Gemini content generation with 5-model fallback chain
│   ├── audio_engine.py           # TTS narration (Gemini TTS → gTTS fallback)
│   ├── video_engine.py           # FFmpeg rendering, stock download, subtitle baking
│   ├── ai_video_engine.py        # Wan 2.1 text-to-video via HF Gradio API
│   ├── animation_engine.py       # Pillow-based motion graphics & overlay renderer
│   ├── youtube_engine.py         # YouTube Data API v3 upload, SEO, localizations
│   └── trends_engine.py          # Trending topic scraper (YT autocomplete, Google Trends)
│
├── utils/                        # Utility Modules
│   ├── auth_youtube.py           # YouTube OAuth2 flow & token management
│   ├── youtube_uploader.py       # Standalone upload helper
│   └── import_token.py           # OAuth token import/migration utility
│
├── assets/                       # Static Assets
│   ├── Watermark/                # Brand watermark overlay (WebP)
│   ├── cta_images/               # Randomized call-to-action end cards
│   └── fonts/                    # Tamil (NotoSansTamil) & Latin (NotoSans) TTF fonts
│
├── credentials/                  # OAuth Secrets (git-ignored)
├── outputs/                      # Rendered videos, thumbnails, ASS tracks (git-ignored)
├── temp/                         # Intermediate processing files (git-ignored)
│
├── Dockerfile                    # Production container (Python 3.12-slim + FFmpeg)
├── docker-compose.yml            # Full stack: PostgreSQL 15 + Bot service
├── requirements.txt              # Python dependencies
└── .env                          # Environment configuration (git-ignored)
```

---

## ⚙️ Tech Stack

| Category | Technologies |
|----------|-------------|
| **Language** | Python 3.10+ |
| **AI Models** | Google Gemini (2.0/2.5/3.1 Flash, Pro), Wan 2.1 (Text-to-Video) |
| **TTS** | Gemini TTS, gTTS |
| **Transcription** | Groq Whisper API |
| **Video Processing** | FFmpeg, Pillow, yt-dlp |
| **Web Framework** | FastAPI + Uvicorn |
| **Bot Framework** | python-telegram-bot |
| **Database** | PostgreSQL 15 + SQLAlchemy (async) |
| **Task Scheduling** | APScheduler (AsyncIO) |
| **Configuration** | Pydantic Settings + python-dotenv |
| **Containerization** | Docker + Docker Compose |
| **Deployment** | Hugging Face Spaces, self-hosted |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ for Kitchaa's Enterprises, Tamil Nadu, India**

</div>
