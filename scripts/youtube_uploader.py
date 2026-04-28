"""
Step 5: YouTube Upload via YouTube Data API v3.
Handles OAuth authentication, video upload, and scheduling.

Quota: 1,600 units per upload → max 6 uploads/day with default 10,000 quota.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)

# OAuth scope for YouTube uploads
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = config.CREDENTIALS_DIR / "youtube_token.json"
CLIENT_SECRET_FILE = config.CREDENTIALS_DIR / "oauth_client_secret.json"


def _get_authenticated_service():
    """
    Create an authenticated YouTube API service.
    First run requires browser-based OAuth login.
    Subsequent runs use cached token (auto-refreshed).
    """
    creds = None

    # Load existing token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired OAuth token...")
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"OAuth client secret not found at {CLIENT_SECRET_FILE}.\n"
                    "Download it from Google Cloud Console:\n"
                    "1. Go to https://console.cloud.google.com/apis/credentials\n"
                    "2. Create OAuth 2.0 Client ID (Desktop App)\n"
                    "3. Download JSON → save as credentials/oauth_client_secret.json"
                )
            logger.info("Starting OAuth flow (browser will open)...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES
            )
            creds = flow.run_local_server(port=8090)

        # Save the token for future use
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        logger.info("OAuth token saved to %s", TOKEN_FILE)

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = None,
    privacy_status: str = None,
    publish_at: str = None,
) -> dict:
    """
    Upload a video to YouTube.

    Args:
        video_path: Path to the video file.
        title: Video title (max 100 chars).
        description: Video description.
        tags: List of tags for SEO.
        category_id: YouTube category ID (default: Education).
        privacy_status: 'public', 'private', or 'unlisted'.
        publish_at: ISO 8601 datetime for scheduled publishing.

    Returns:
        Dict with upload result (video ID, URL, etc.)
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    youtube = _get_authenticated_service()

    # Prepare metadata
    category_id = category_id or config.YOUTUBE_CATEGORY_ID
    privacy_status = privacy_status or config.YOUTUBE_PRIVACY_STATUS

    # Ensure title has #Shorts for Shorts shelf
    if "#Shorts" not in title and "#shorts" not in title:
        title = f"{title} #Shorts"

    # Truncate title to YouTube's limit
    if len(title) > 100:
        title = title[:97] + "..."

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags[:500],  # YouTube allows up to 500 chars of tags
            "categoryId": category_id,
            "defaultLanguage": config.YOUTUBE_DEFAULT_LANGUAGE,
            "defaultAudioLanguage": config.YOUTUBE_DEFAULT_LANGUAGE,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    # Add scheduled publish time if provided
    if publish_at and privacy_status == "private":
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at

    # Create media upload
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024,  # 1MB chunks
    )

    logger.info("📤 Uploading: %s", title)

    # Execute upload with retry
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = _resumable_upload(request)

    video_id = response.get("id", "unknown")
    result = {
        "video_id": video_id,
        "url": f"https://youtube.com/shorts/{video_id}",
        "title": title,
        "status": response.get("status", {}).get("uploadStatus", "unknown"),
        "uploaded_at": datetime.now().isoformat(),
    }

    logger.info("✅ Uploaded! URL: %s", result["url"])
    return result


def _resumable_upload(request, max_retries: int = 3) -> dict:
    """Execute a resumable upload with retry logic."""
    response = None
    retry = 0

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                logger.info("Upload progress: %d%%", int(status.progress() * 100))
        except Exception as e:
            if retry < max_retries:
                retry += 1
                sleep_time = 2 ** retry  # Exponential backoff
                logger.warning(
                    "Upload error (retry %d/%d in %ds): %s",
                    retry, max_retries, sleep_time, e,
                )
                time.sleep(sleep_time)
            else:
                raise

    return response


def _build_description(script: dict) -> str:
    """Build a YouTube-optimized description from script metadata."""
    hashtags = " ".join(script.get("hashtags", ["#Shorts", "#CivilEngineering", "#Tamil"]))
    keywords = ", ".join(script.get("keywords", []))
    search_tags = script.get("search_tags", "")

    description = f"""{script.get('hook', '')}

🏗️ Civil Engineering tips in Tamil!
📚 Daily education shorts for aspiring engineers

{hashtags}

Keywords: {keywords}
{search_tags}

👉 Follow for daily civil engineering tips!
🔔 Like & Share to support!

---
© {config.CHANNEL_NAME}
"""
    return description.strip()


# ── Schedule Management ───────────────────────────────

def load_upload_schedule() -> dict:
    """Load or create the upload schedule."""
    schedule_file = config.DATA_DIR / "upload_schedule.json"

    if schedule_file.exists():
        return json.loads(schedule_file.read_text(encoding="utf-8"))

    # Create new schedule (daily starting tomorrow)
    schedule = {}
    start_date = datetime.now() + timedelta(days=1)

    for day in range(1, config.TOTAL_DAYS + 1):
        upload_date = start_date + timedelta(days=day - 1)
        schedule[str(day)] = {
            "date": upload_date.strftime("%Y-%m-%d"),
            "time": config.UPLOAD_TIME_IST,
            "status": "pending",
            "video_id": None,
            "url": None,
        }

    schedule_file.write_text(
        json.dumps(schedule, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return schedule


def save_upload_schedule(schedule: dict) -> None:
    """Save the upload schedule."""
    schedule_file = config.DATA_DIR / "upload_schedule.json"
    schedule_file.write_text(
        json.dumps(schedule, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def upload_today(scripts: list[dict]) -> dict | None:
    """
    Upload today's scheduled video.

    Returns:
        Upload result dict or None if nothing to upload.
    """
    schedule = load_upload_schedule()
    today = datetime.now().strftime("%Y-%m-%d")

    for day_str, entry in schedule.items():
        if entry["date"] == today and entry["status"] == "pending":
            day = int(day_str)
            day_dir = config.OUTPUT_DIR / f"day_{day:02d}"
            video_path = day_dir / "final_video.mp4"

            if not video_path.exists():
                logger.error("Video not found for day %d: %s", day, video_path)
                return None

            # Get script data
            script = scripts[day - 1] if day <= len(scripts) else {}

            # Build metadata
            title = script.get("title", f"Civil Engineering Tip #{day} #Shorts")
            description = _build_description(script)
            tags = script.get("keywords", []) + ["Shorts", "CivilEngineering", "Tamil"]

            # Upload
            result = upload_video(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
            )

            # Update schedule
            entry["status"] = "uploaded"
            entry["video_id"] = result["video_id"]
            entry["url"] = result["url"]
            save_upload_schedule(schedule)

            return result

    logger.info("No videos scheduled for upload today (%s)", today)
    return None


def get_upload_status() -> dict:
    """Get summary of upload schedule status."""
    schedule = load_upload_schedule()
    summary = {"pending": 0, "uploaded": 0, "failed": 0, "total": len(schedule)}

    for entry in schedule.values():
        status = entry.get("status", "pending")
        summary[status] = summary.get(status, 0) + 1

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test authentication
    print("🔐 Testing YouTube authentication...")
    try:
        service = _get_authenticated_service()
        print("✅ YouTube API authenticated successfully!")
    except FileNotFoundError as e:
        print(f"⚠️ {e}")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")

    # Show schedule status
    status = get_upload_status()
    print(f"\n📊 Upload Schedule: {status}")
