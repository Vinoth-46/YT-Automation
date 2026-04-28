"""
Central configuration for YouTube Shorts Pipeline.
All paths, API settings, and constants live here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

import threading
load_dotenv()

# Global lock to prevent multiple FFmpeg processes (OOM prevention)
RENDER_LOCK = threading.Lock()

# ── Paths ─────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
SCRIPTS_DIR = BASE_DIR / "scripts"
PROMPTS_DIR = BASE_DIR / "prompts"
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
CREDENTIALS_DIR = BASE_DIR / "credentials"
LOGS_DIR = BASE_DIR / "logs"

# Cross-platform font path
if os.path.exists("/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf"):
    # Google Colab path
    FONT_PATH = Path("/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf")
else:
    # Windows/Local path
    FONT_PATH = ASSETS_DIR / "fonts" / "NotoSansTamil-Bold.ttf"
WATERMARK_PATH = ASSETS_DIR / "watermark" / "channel_logo.png"
BGM_PATH = ASSETS_DIR / "music" / "background.mp3"

# ── API Keys ──────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")

# ── OpenRouter Settings ───────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openrouter/free"  # Auto-routes to the best available free model
OPENROUTER_FALLBACK_MODEL = "qwen/qwen-2.5-72b-instruct:free"  # More stable free fallback

# ── Gemini TTS Settings ──────────────────────────────
GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
GEMINI_TTS_VOICE = "Achernar"  # Premium Tamil-compatible voice
GEMINI_TTS_FALLBACK = True  # Fall back to edge-tts if Gemini fails

# ── Edge-TTS Settings (Fallback) ─────────────────────
EDGE_TTS_VOICE = "ta-IN-PallaviNeural"  # Tamil female neural voice
EDGE_TTS_RATE = "+10%"  # Slightly faster for Shorts punchiness
EDGE_TTS_PITCH = "+0Hz"

# ── Pexels Settings ──────────────────────────────────
PEXELS_BASE_URL = "https://api.pexels.com/videos"
PEXELS_RESULTS_PER_QUERY = 5
PEXELS_MIN_DURATION = 5  # seconds
PEXELS_ORIENTATION = "portrait"  # Vertical for Shorts

# ── Video Settings ────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_MAX_DURATION = 180.0  # YouTube Shorts max limit is 3 minutes (180s)
VIDEO_CODEC = "libx264"
VIDEO_AUDIO_CODEC = "aac"
VIDEO_AUDIO_BITRATE = "192k"
VIDEO_BITRATE = "5M"

# ── Split-Screen Layout ──────────────────────────────
AVATAR_SPLIT_RATIO = 0.5      # Top 50% = avatar, Bottom 50% = footage
AVATAR_HEIGHT = int(VIDEO_HEIGHT * AVATAR_SPLIT_RATIO)  # 960px
FOOTAGE_HEIGHT = VIDEO_HEIGHT - AVATAR_HEIGHT             # 960px

# ── Subtitle Settings (Premium Tamil) ────────────────
SUBTITLE_FONT_SIZE = 70
SUBTITLE_FONT_NAME = "Noto Sans Tamil"
SUBTITLE_PRIMARY_COLOR = "&H00FFFFFF"    # White text
SUBTITLE_OUTLINE_COLOR = "&H00000000"    # Black outline
SUBTITLE_SHADOW_COLOR = "&H80000000"     # Semi-transparent black shadow
SUBTITLE_OUTLINE_WIDTH = 4
SUBTITLE_SHADOW_DEPTH = 3
SUBTITLE_MARGIN_BOTTOM = 150  # px from bottom of screen (over footage)

# ── BGM Settings ──────────────────────────────────────
BGM_VOLUME_DB = -18  # Ducked under voiceover
VOICE_VOLUME_DB = 0

# ── YouTube Upload Settings ──────────────────────────
YOUTUBE_CATEGORY_ID = "27"  # Education
YOUTUBE_PRIVACY_STATUS = "private"  # Upload as private first
YOUTUBE_DEFAULT_LANGUAGE = "ta"  # Tamil
YOUTUBE_UPLOAD_QUOTA_COST = 1600  # Units per upload
YOUTUBE_DAILY_QUOTA = 10000

# ── Channel Branding ─────────────────────────────────
CHANNEL_NAME = "Kitcha Enterprises"  # Updated channel name
UPLOAD_TIME_IST = "18:00"  # 6 PM IST daily

# ── Batch & Bot Settings ──────────────────────────────
TOTAL_DAYS = 1
VISUAL_PLAN_BATCH_SIZE = 1  # Scripts per visual plan API call
BOT_STATE_FILE = DATA_DIR / "bot_state.json"
CURRENT_MONTH = 1
VIDEO_MODE = "avatar"  # "avatar" or "footage_only"

# ── Ensure directories exist ─────────────────────────
for d in [OUTPUT_DIR, DATA_DIR, CREDENTIALS_DIR, LOGS_DIR,
          ASSETS_DIR / "fonts", ASSETS_DIR / "music",
          ASSETS_DIR / "watermark", ASSETS_DIR / "templates"]:
    d.mkdir(parents=True, exist_ok=True)
