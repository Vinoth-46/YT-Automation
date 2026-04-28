"""
youtube_uploader.py  +  telegram_notifier.py
=============================================
YouTube Data API v3 — free (10,000 units/day)
Telegram Bot API     — free (unlimited)
"""

# ════════════════════════════════════════════════════════════════
#  YOUTUBE UPLOADER
# ════════════════════════════════════════════════════════════════

import os
import time
import requests
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from config import (
    YOUTUBE_CLIENT_SECRETS, YOUTUBE_TOKEN_FILE,
    YOUTUBE_CATEGORY_ID, YOUTUBE_PRIVACY,
    PUBLISH_HOUR_IST, PUBLISH_MINUTE_IST,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CHANNEL_NAME
)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
IST = timezone(timedelta(hours=5, minutes=30))


def _get_youtube():
    creds = None
    os.makedirs(os.path.dirname(YOUTUBE_TOKEN_FILE), exist_ok=True)
    if os.path.exists(YOUTUBE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(YOUTUBE_TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(YOUTUBE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    is_short: bool = False,
    publish_now: bool = True,
) -> str:
    """Upload video/Short to YouTube. Returns watch URL."""
    youtube = _get_youtube()

    body = {
        "snippet": {
            "title": (title[:95] + " #Shorts" if is_short and "#Shorts" not in title else title)[:100],
            "description": description[:5000],
            "tags": (tags + ["Shorts", "YouTubeShorts"])[:500] if is_short else tags[:500],
            "categoryId": YOUTUBE_CATEGORY_ID,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": "public" if publish_now else "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"  Uploading {'Short' if is_short else 'video'}: {os.path.basename(video_path)}")
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True,
                            chunksize=50 * 1024 * 1024)
    req = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    retries  = 0
    while response is None:
        try:
            status, response = req.next_chunk()
            if status:
                print(f"\r  Upload: {int(status.progress()*100)}%", end="", flush=True)
        except Exception as e:
            retries += 1
            if retries > 5:
                raise RuntimeError(f"Upload failed: {e}")
            time.sleep(2 ** retries)

    video_id = response["id"]
    url = f"https://www.youtube.com/{'shorts/' if is_short else 'watch?v='}{video_id}"
    print(f"\n  ✓ {'Short' if is_short else 'Video'} live: {url}")
    return url


def youtube_auth_once():
    """Run this once in terminal to authenticate your YouTube channel."""
    yt = _get_youtube()
    ch = yt.channels().list(part="snippet", mine=True).execute()
    if ch.get("items"):
        name = ch["items"][0]["snippet"]["title"]
        print(f"✓ Authenticated as: {name}")
    else:
        print("✗ No channel found.")


# ════════════════════════════════════════════════════════════════
#  TELEGRAM NOTIFIER
# ════════════════════════════════════════════════════════════════

_TG_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def _send(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"  [Telegram disabled — no token]")
        return False
    try:
        r = requests.post(
            f"{_TG_URL}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
                  "parse_mode": "Markdown", "disable_web_page_preview": False},
            timeout=20
        )
        return r.status_code == 200
    except Exception as e:
        print(f"  Telegram error: {e}")
        return False


def notify_published(day: int, title: str, url: str, short_url: str = None):
    now = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    msg = (
        f"🎬 *Video Published — Day {day}/30*\n\n"
        f"📺 *{CHANNEL_NAME}*\n"
        f"*{title}*\n\n"
        f"🔗 [Watch on YouTube]({url})"
    )
    if short_url:
        msg += f"\n📱 [YouTube Short]({short_url})"
    msg += f"\n\n⏰ {now}\n_Day {day} complete ✓_"
    _send(msg)


def notify_generating(day: int, title: str):
    _send(f"⚙️ *Generating Day {day}/30*\n_{title}_\nRendering now...")


def notify_error(day: int, stage: str, error: str):
    _send(f"⚠️ *Error — Day {day} @ {stage}*\n`{error[:300]}`")


def notify_start():
    _send(
        f"🚀 *{CHANNEL_NAME} Automation Started*\n"
        f"30-day pipeline running.\nDaily post: {PUBLISH_HOUR_IST:02d}:00 IST\n"
        f"Free stack: Llama 3.1 + XTTS v2 + SadTalker + Whisper 🏗️"
    )
