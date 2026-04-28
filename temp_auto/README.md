# Civil Build TV — 100% Free YouTube Automation
## Tamil Nadu Civil Engineering Channel | Daily Auto-Publishing

> **Every tool in this stack is completely free and open-source.**
> No subscriptions, no API credits, no HeyGen, no ElevenLabs.

---

## 🎯 What This System Does

| Step | Free Tool | What It Produces |
|------|-----------|-----------------|
| Script | HuggingFace (Llama 3.1 8B) | 30 full civil engineering scripts |
| Voice | Coqui XTTS v2 (local) | Natural human-like English + Tamil intro audio |
| Talking Head | SadTalker (local) | Realistic human face speaking with lip-sync |
| Captions | Whisper + IndicTrans2 | Dual English+Tamil burned-in subtitles |
| Background | Pexels API (free) | Construction site B-roll composited behind presenter |
| Upload | YouTube Data API v3 | Auto-publish daily at 10 AM IST |
| Alert | Telegram Bot | URL sent to you after each publish |

---

## 🏗️ System Requirements

- **OS**: Ubuntu 20.04+ / Debian (a ₹500/month VPS works)
- **RAM**: 8 GB minimum (16 GB recommended for GPU)
- **Storage**: 50 GB (for models + 30 days of video)
- **GPU**: Optional but makes XTTS + Whisper 5× faster (any NVIDIA)
- **Python**: 3.10+
- **FFmpeg**: Required for video composition

---

## 📦 One-Time Setup (Run These Once)

### Step 1 — Install system packages

```bash
sudo apt update
sudo apt install -y ffmpeg python3-pip git screen fonts-lohit-taml
pip install --upgrade pip
```

### Step 2 — Install Python dependencies

```bash
pip install -r requirements.txt

# For GPU (CUDA 12.1) — much faster:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# For CPU only:
pip install torch torchvision torchaudio
```

### Step 3 — Install SadTalker (realistic talking head)

```bash
git clone https://github.com/OpenTalker/SadTalker.git
cd SadTalker
pip install -r requirements.txt
bash scripts/download_models.sh     # downloads ~2 GB weights (free)
cd ..
```

SadTalker uses **RestoreFormer** face enhancement — this is what makes
the face look indistinguishable from a real person on camera.

### Step 4 — Get your avatar photo

**Option A (easiest):** Go to https://thispersondoesnotexist.com
- Refresh the page until you find a face that looks like a professional
- Right-click → Save as `data/avatars/presenter.jpg`
- Pick someone who looks like a civil engineer (professional, trustworthy)

**Option B (use yourself):**
- Take a clear front-facing photo in good lighting
- Set `AVATAR_PHOTO=path/to/your/photo.jpg`
- Your face will appear in every video — fully automated

**Option C (generate with Stable Diffusion):**
```bash
# If you have Stable Diffusion locally:
# Prompt: "professional male civil engineer, indian, front facing, white background,
#          studio lighting, realistic, 512x512, no glasses"
```

### Step 5 — Set up voice (voice clone for maximum realism)

XTTS v2 can clone any voice from a 6-second audio sample.

```bash
# Record yourself (or anyone) reading this sentence clearly:
# "Welcome to Civil Build TV. Today we will learn about construction
#  techniques that will save you time and money on your building project."

# Save as: data/voice_sample.wav  (WAV format, any sample rate)
# Set in .env:
# VOICE_CLONE_WAV=data/voice_sample.wav
```

With voice clone, the AI voice sounds **exactly** like the recorded person —
not robotic, not synthetic — genuinely indistinguishable from a real human.

### Step 6 — Configure environment variables

```bash
cp .env.example .env
nano .env     # fill in all values
```

Required:
- `HF_API_TOKEN` — from https://huggingface.co/settings/tokens (free)
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — from @BotFather
- `PEXELS_API_KEY` — from https://www.pexels.com/api/ (free)
- `SADTALKER_DIR` — path to your cloned SadTalker folder
- `AVATAR_PHOTO` — path to presenter portrait

### Step 7 — YouTube OAuth2 (one-time browser login)

1. Go to https://console.cloud.google.com
2. Create project → APIs & Services → Enable "YouTube Data API v3"
3. Credentials → Create OAuth2 Client ID → Desktop application → Download JSON
4. Save as `credentials.json` in project root
5. Run: `python main.py --auth-youtube` (browser opens, sign into your channel)

---

## 🚀 Running the System

```bash
# Generate all 30 scripts + pre-generate Day 1 (run once)
python main.py --init

# Start the scheduler in a persistent screen session
screen -S civil-tv
python main.py --start
# Press Ctrl+A then D to detach (keeps running after you close terminal)

# Check progress anytime
python main.py --status

# Re-attach later
screen -r civil-tv
```

---

## 📅 What Happens Each Day

```
00:00 AM IST  → Generate tomorrow's video:
                  XTTS v2 voice (English + Tamil intro)
                  SadTalker talking head
                  Whisper transcription → IndicTrans2 Tamil translation → ASS captions
                  Pexels background download

10:00 AM IST  → Compose final video (FFmpeg):
                  Talking head composited on construction background
                  Dual-language captions burned in
                  Upload to YouTube (main + Short)
                  Telegram notification with live URL
```

---

## 🎬 Caption Style

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Civil Build TV                                             │
│                                                             │
│  [Construction site background]                             │
│                                                             │
│  [Talking head — bottom right]                              │
│                                                             │
│  நீங்கள் வீடு கட்டும் முன்பு மண் சோதனை செய்யுங்கள்          │  ← Tamil (yellow)
│  Test your soil before construction begins                  │  ← English (white)
└─────────────────────────────────────────────────────────────┘
```

---

## 💰 Cost Breakdown

| Tool | Cost |
|------|------|
| HuggingFace Inference API | FREE (1000 req/day) |
| Coqui XTTS v2 | FREE (runs locally) |
| SadTalker | FREE (runs locally) |
| OpenAI Whisper | FREE (runs locally) |
| AI4Bharat IndicTrans2 | FREE (HF API) |
| Pexels API | FREE (unlimited) |
| YouTube Data API v3 | FREE (10K units/day) |
| Telegram Bot | FREE (unlimited) |
| **Total** | **₹0 / month** |

Only cost: VPS to run it 24/7 (~₹400-800/month on DigitalOcean/Hetzner)

---

## 📂 Project Structure

```
civil_build_free/
├── main.py                ← Entry point + APScheduler
├── config.py              ← All settings and model paths
├── content_planner.py     ← Llama 3.1 script generation + SEO
├── voice_generator.py     ← Coqui XTTS v2 voice synthesis
├── talking_head.py        ← SadTalker talking head + face enhancement
├── caption_generator.py   ← Whisper + IndicTrans2 + ASS subtitles
├── video_composer.py      ← FFmpeg composition pipeline
├── youtube_uploader.py    ← YouTube API v3 + Telegram notifications
├── requirements.txt
├── .env.example
├── credentials.json       ← YouTube OAuth2 (you download this)
└── data/
    ├── scripts.json       ← All 30 generated scripts
    ├── progress.json      ← Day counter + completed list
    ├── audio/             ← XTTS voice files
    ├── videos/            ← Final composed main videos
    ├── shorts/            ← Final composed Shorts
    ├── captions/          ← Whisper transcripts + ASS files
    ├── avatars/           ← Presenter photo
    └── backgrounds/       ← Pexels B-roll videos
```

---

## 🔧 Troubleshooting

**XTTS slow on CPU?**
→ Get a GPU VPS (Vast.ai has cheap GPU rentals from ₹50/hour)
→ Or run generation on your PC and upload output to VPS

**SadTalker face looks unreal?**
→ Use a higher quality portrait photo (512×512+, good lighting)
→ Make sure `SADTALKER_ENHANCER=RestoreFormer` is set

**Tamil captions wrong?**
→ IndicTrans2 is best, but if HF free tier is slow, try local install:
  `pip install indic-trans` (AI4Bharat's local package)

**YouTube quota exceeded (10,000 units)?**
→ Each upload = ~1600 units → max ~6 uploads/day on free quota
→ Apply for higher quota at Google Cloud Console (free, takes 1-2 days)
