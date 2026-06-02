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

# 🎬 YT Shorts Automation Bot — Civil Engineering Pipeline

A high-performance, fully automated pipeline designed to generate, voice, caption, edit, and upload highly optimized bilingual YouTube Shorts for the civil engineering and home construction niche. 

Specifically tailored for **Kitchaa's Enterprises (Tamil Nadu, India)** to maximize organic search discoverability and viewer retention.

---

## ✨ Features & Architecture

### 1. 🤖 AI Content & Narration Engine
* **Mega-Prompt Content Generation:** Creates high-retention structural plans, concrete advice, material selection (e.g., M-sand vs. river sand, brick vs. block), Vastu architecture, and Tamil Nadu residential building tips.
* **5-Model Fallback Chain:** Automatically rotates Gemini API keys and rolls back through robust models (`gemini-2.5-flash` ➔ `gemini-2.0-flash` ➔ `gemini-2.5-flash-preview` ➔ `gemini-2.0-flash-lite` ➔ `gemini-2.5-pro`) to eliminate 429 quota exhaustion and 503 service busy errors.
* **Gemini TTS Integration:** Generates natural Tamil voiceovers using rotated Gemini speech-to-text key quotas.

### 2. 📺 Visual Acquisition & Smart Downloader
* **YouTube CC Stock Downloader:** Features a high-relevance search engine powered by `yt-dlp` to download real-world construction clips from YouTube (bypassing generic stock API limits).
* **0% Repeated Clips Guarantee:** 
  * Dynamically queries YouTube search results by scene index (`ytsearch1`, `ytsearch2`, `ytsearch3`, etc.), ensuring every scene gets a **completely unique video clip** even when using fallback search terms.
  * Dynamically cuts video clips at varying offsets (`start_sec = 3 + (scene_index * 2)`) to avoid repeated visual loops.
  * Standard Pexels and Pixabay stock libraries remain available as alternative sources.

### 3. 🎥 High-Retention Video & Subtitle Render
* **HD Standardisation:** FFmpeg processes all clips to **vertical 1080x1920 HD** format, crops/centers landscape footage, scales/places your custom business watermark, and concatenates clips seamlessly.
* **Pro Subtitle Overlays (Bilingual):** Transcribes Tamil audio to English Closed Captions (`.srt`) in 4 seconds via Groq Whisper API (with Gemini audio upload fallback).
* **Baked Subtitle Overlays:** Automatically converts SRT captions into stylized ASS Tamil subtitle overlay cards (`Nirmala UI` font, custom yellow colors, bold outlines, and safe-zone margins).
* **Click-Through Rate (CTR) Thumbnails:** Grabs a frame at `3.0s` (hook peak) and renders large, capitalized clickbaity text overlays (`120px` bold Arial) to capture mobile recommendations.

### 4. 📈 Organic Reach & SEO Optimization
* **Algorithm-Aligned Metadata:** Dynamically injects `defaultLanguage: 'ta'` and `defaultAudioLanguage: 'ta'` into YouTube Snippets so initial impressions target Tamil-speaking feeds instead of being wasted.
* **Double-Indexing (Bilingual):** Generates titles in dynamic Tamil & English formats (e.g., `வீடு கட்டும் தவறு | Avoid This Building Mistake`) to rank for bilingual search terms.
* **H.264 Quality Boost:** Encodes streams at `CRF 23` (YouTube's recommended sweet spot) using `high` profile level `4.1` with B-frames, eliminating blurry pixel blocks.
* **Clean Descriptions & Localization:** Keeps the public description professional and clean. Multilingual translations (Hindi, Spanish, Tamil) are automatically uploaded using the official YouTube Localizations API.
* **Strategic Hashtags:** Forces `#Shorts` and your top 3 niche keywords to the very start of the description to show up as clickable blue links above the title.

### 5. 🤖 Interactive Telegram Control Bot
* `/generate` — Triggers a live video generation job immediately with active stage progress.
* `/status` — Checks the status of recent video generation and upload jobs.
* `/schedule` — Schedules standard daily postings in **IST (Indian Standard Time)**.
* `/view_schedule` — View active posting timelines.
* `/clearschedule` — Wipe and clear all active schedulers.
* `/autopost` — Toggles auto-approval mode on or off.

---

## 🛠️ Installation & Setup

### Prerequisites
* Python 3.10+
* **FFmpeg & FFprobe:** Installed and added to system PATH.
* **yt-dlp:** Installed on system (`pip install yt-dlp`).

### Setup Instructions
1. **Clone the repository:**
   ```bash
   git clone https://github.com/Vinoth-46/YT-Automation.git
   cd YT-Automation
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create a `.env` file in the root folder based on this structure:
   ```env
   # API Keys
   OPENROUTER_API_KEY=your_openrouter_key
   PEXELS_API_KEY=your_pexels_key
   PIXABAY_API_KEY=your_pixabay_key
   GEMINI_API_KEY=key_1,key_2,key_3 # Support multiple rotated keys
   GROQ_API_KEY=your_groq_key
   
   # Telegram
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=user_id_1,user_id_2
   
   # Database
   POSTGRES_URL=postgresql+asyncpg://user:pass@host:port/dbname
   
   # Video Engine Configuration
   SUBTITLE_MODE=baked # 'baked' for styled ASS subtitles, 'cc' for clean upload
   VIDEO_SOURCE=youtube # 'youtube' for Creative Commons clips, 'pexels' for stock
   ```

4. **Initialize Database:**
   ```bash
   python -c "import asyncio; from core.database import init_db; asyncio.run(init_db())"
   ```

---

## 🚀 Running the Bot & Pipeline

### Run Telegram Bot
To start the Telegram daemon locally:
```bash
python bot/main.py
```

### Direct Video Generation Test
To test the pipeline directly in your terminal with the new YouTube search and download downloader:
```bash
python scratch/test_generate_youtube.py
```
This script bypasses stock APIs, searches YouTube for Creative Commons clips, cuts them dynamically, renders vertical HD mp4 with subtitles, and generates a CTR-optimized thumbnail.

---

## 📂 Project Structure
```
├── assets/
│   ├── Watermark/       # loading-logo.webp applied to all videos
│   ├── cta_images/      # End graphics chosen randomly for CTA
│   └── fonts/           # Auto-downloaded Tamil & English TTF fonts
├── bot/
│   ├── main.py          # Telegram bot initialization
│   └── handlers.py      # Commands (/generate, /status, /schedule, etc.)
├── core/
│   ├── config.py        # System configuration schema
│   ├── database.py      # SQLAlchemy connection
│   ├── models.py        # Database models (Job, ScriptAsset, etc.)
│   └── orchestrator.py  # Automation pipeline lifecycle
├── engines/
│   ├── script_engine.py # AI script generator & model fallbacks
│   ├── audio_engine.py  # Gemini TTS speech engine
│   └── video_engine.py  # FFmpeg renderer & yt-dlp downloader
├── outputs/             # Rendered videos, thumbnails, and ASS tracks
└── scratch/             # Temporary validation and migration utilities
```

---

## 📝 License
This project is licensed under the MIT License.
