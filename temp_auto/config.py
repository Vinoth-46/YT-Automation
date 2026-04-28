"""
Civil Build TV — 100% Free Stack Configuration
================================================
Every model and API used here is completely free.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# CHANNEL IDENTITY
# ─────────────────────────────────────────────────────────────────────────────
CHANNEL_NAME   = "Civil Build TV"
CHANNEL_LANG_1 = "English"
CHANNEL_LANG_2 = "Tamil"
TARGET_AUDIENCE = "homeowners and people planning to build a house in Tamil Nadu, India"

# ─────────────────────────────────────────────────────────────────────────────
# FREE SCRIPT GENERATION — HuggingFace Inference API
# Free tier: 1000 requests/day  |  Model: Meta Llama 3.1 8B Instruct
# Get key at: https://huggingface.co/settings/tokens  (free account)
# ─────────────────────────────────────────────────────────────────────────────
HF_API_TOKEN          = os.getenv("HF_API_TOKEN", "")
HF_SCRIPT_MODEL       = "meta-llama/Meta-Llama-3.1-8B-Instruct"   # free inference
HF_FALLBACK_MODEL     = "mistralai/Mistral-7B-Instruct-v0.3"       # fallback
HF_INFERENCE_URL      = "https://api-inference.huggingface.co/models"

# ─────────────────────────────────────────────────────────────────────────────
# FREE VOICE — Coqui XTTS v2  (runs locally, completely free)
# Extremely natural, human-like, multilingual (supports Tamil & English)
# Install: pip install TTS
# Model auto-downloads on first run (~1.8 GB)
# ─────────────────────────────────────────────────────────────────────────────
TTS_MODEL             = "tts_models/multilingual/multi-dataset/xtts_v2"
TTS_SPEAKER           = "Claribel Dervla"   # warm, clear, human-like English voice
TTS_LANGUAGE_EN       = "en"
TTS_LANGUAGE_TA       = "ta"                # Tamil supported by XTTS v2
TTS_SAMPLE_RATE       = 24000
# Optional: clone from a 6-second WAV of a real person's voice
VOICE_CLONE_WAV       = os.getenv("VOICE_CLONE_WAV", "")  # path to your voice sample

# ─────────────────────────────────────────────────────────────────────────────
# FREE REALISTIC TALKING HEAD — SadTalker (HuggingFace Space + local)
# Animates a portrait photo to speak in sync with audio
# Paper: https://arxiv.org/abs/2211.12194
# HF Space: https://huggingface.co/spaces/vinthony/SadTalker
# Local install: git clone https://github.com/OpenTalker/SadTalker
# ─────────────────────────────────────────────────────────────────────────────
SADTALKER_DIR         = os.getenv("SADTALKER_DIR", "./SadTalker")
SADTALKER_ENHANCER    = "RestoreFormer"    # face enhancer for ultra-realistic output
SADTALKER_PREPROCESS  = "full"             # full-body or face
SADTALKER_STILL_MODE  = False              # False = natural head movement
SADTALKER_EXP_SCALE   = 1.0               # expression strength
# Avatar photo — AI-generated realistic person (free from thispersondoesnotexist.com)
# or generate with Stable Diffusion locally
AVATAR_PHOTO          = os.getenv("AVATAR_PHOTO", "data/avatars/presenter.jpg")

# ─────────────────────────────────────────────────────────────────────────────
# FREE FACE ENHANCEMENT — GFPGAN / CodeFormer (bundled with SadTalker)
# Upscales and enhances face details for cinematic realism
# ─────────────────────────────────────────────────────────────────────────────
ENHANCE_FACE          = True
FACE_ENHANCER         = "RestoreFormer"    # or "CodeFormer"

# ─────────────────────────────────────────────────────────────────────────────
# FREE TRANSCRIPTION — OpenAI Whisper (runs locally, 100% free)
# Used to get word-level timestamps for caption generation
# Install: pip install openai-whisper
# Model: "medium" — best balance of accuracy and speed
# ─────────────────────────────────────────────────────────────────────────────
WHISPER_MODEL         = "medium"           # tiny/base/small/medium/large
WHISPER_LANGUAGE      = "en"

# ─────────────────────────────────────────────────────────────────────────────
# FREE TRANSLATION — AI4Bharat IndicTrans2 (HuggingFace, free)
# Best-in-class English → Tamil translation, trained on Indian languages
# Model: ai4bharat/indictrans2-en-indic-1B (free HF inference or local)
# ─────────────────────────────────────────────────────────────────────────────
TRANSLATION_MODEL     = "ai4bharat/indictrans2-en-indic-1B"
HF_TRANSLATION_URL    = f"{HF_INFERENCE_URL}/{TRANSLATION_MODEL}"
# Fallback: Helsinki-NLP opus-mt model (lighter, also free)
TRANSLATION_FALLBACK  = "Helsinki-NLP/opus-mt-en-mul"

# ─────────────────────────────────────────────────────────────────────────────
# FREE BACKGROUND VIDEO — Pexels API (free tier: unlimited)
# Construction site, building, materials B-roll
# Get key at: https://www.pexels.com/api/
# ─────────────────────────────────────────────────────────────────────────────
PEXELS_API_KEY        = os.getenv("PEXELS_API_KEY", "")
PEXELS_SEARCH_TERMS   = [
    "construction site", "concrete foundation", "brick wall construction",
    "building materials", "civil engineering", "house construction India",
    "cement mixing", "steel reinforcement", "roof construction"
]

# ─────────────────────────────────────────────────────────────────────────────
# FREE UPLOAD — YouTube Data API v3 (free, 10,000 units/day quota)
# Setup: https://console.cloud.google.com → Enable YouTube Data API v3
# ─────────────────────────────────────────────────────────────────────────────
YOUTUBE_CLIENT_SECRETS = "credentials.json"
YOUTUBE_TOKEN_FILE     = "data/youtube_token.json"
YOUTUBE_CATEGORY_ID    = "28"              # Science & Technology
YOUTUBE_PRIVACY        = "public"
PUBLISH_HOUR_IST       = 10               # 10:00 AM IST
PUBLISH_MINUTE_IST     = 0

# ─────────────────────────────────────────────────────────────────────────────
# FREE NOTIFICATION — Telegram Bot (free)
# ─────────────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "")

# ─────────────────────────────────────────────────────────────────────────────
# VIDEO SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
VIDEO_WIDTH           = 1920
VIDEO_HEIGHT          = 1080
VIDEO_FPS             = 25
SHORT_WIDTH           = 1080
SHORT_HEIGHT          = 1920
SHORTS_MAX_SECONDS    = 58

# ─────────────────────────────────────────────────────────────────────────────
# CAPTION STYLE
# ─────────────────────────────────────────────────────────────────────────────
CAPTION_EN_FONT       = "Arial-Bold"
CAPTION_TA_FONT       = "Lohit-Tamil"     # free Tamil font (apt install fonts-lohit-taml)
CAPTION_EN_SIZE       = 52               # px font size on 1080p
CAPTION_TA_SIZE       = 48
CAPTION_EN_COLOR      = "&H00FFFFFF"      # white (ASS format)
CAPTION_TA_COLOR      = "&H0000FFFF"      # yellow for Tamil line
CAPTION_OUTLINE       = "&H00000000"      # black outline
CAPTION_OUTLINE_WIDTH = 3
CAPTION_BOTTOM_EN     = 60               # px from bottom for English
CAPTION_BOTTOM_TA     = 120              # px above English for Tamil

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
DATA_DIR      = "data"
AUDIO_DIR     = "data/audio"
VIDEO_DIR     = "data/videos"
SHORTS_DIR    = "data/shorts"
FRAMES_DIR    = "data/frames"
CAPTIONS_DIR  = "data/captions"
AVATARS_DIR   = "data/avatars"
LOGS_DIR      = "logs"
SCRIPTS_FILE  = "data/scripts.json"
PROGRESS_FILE = "data/progress.json"
BG_VIDEOS_DIR = "data/backgrounds"

BUFFER_DAYS   = 1   # generate N days before publish
