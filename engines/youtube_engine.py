import os
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from core.config import settings
from core.database import Database
from sqlalchemy import update
import json

logger = logging.getLogger(__name__)

class YouTubeEngine:
    def __init__(self, token_data=None):
        self.credentials = None
        self.youtube = None
        
        if token_data:
            self.credentials = Credentials.from_authorized_user_info(token_data, settings.YOUTUBE_SCOPES)
            self._refresh_if_needed()
            self.youtube = build("youtube", "v3", credentials=self.credentials)

    def _refresh_if_needed(self):
        """Refresh OAuth tokens if expired."""
        if self.credentials and self.credentials.expired and self.credentials.refresh_token:
            try:
                self.credentials.refresh(Request())
                logger.info("YouTube OAuth token refreshed successfully")
            except Exception as e:
                logger.error(f"Failed to refresh YouTube token: {e}")
                if "invalid_grant" in str(e).lower():
                    logger.warning("Token is invalid/revoked. Clearing credentials to force re-authentication.")
                    self.credentials = None
                    self.youtube = None

    def upload_video(self, file_path, title, description, tags=None, category_id="27", privacy_status="private"):
        """Upload video to YouTube."""
        if not self.youtube:
            logger.error("YouTube client not initialized. Authenticate first.")
            return None

        # Sanitize and truncate title to YouTube's strict 100 character limit
        safe_title = title.replace("<", "").replace(">", "")
        if len(safe_title) > 95:
            safe_title = safe_title[:95] + "..."

        # Build visible hashtag string (appended to description) AND safe_tags (YouTube metadata)
        hashtag_str = ""
        safe_tags = []
        current_tag_len = 0
        if tags:
            formatted_tags = []
            for tag in tags:
                clean = tag.strip().lstrip("#").replace(" ", "")
                if clean:
                    formatted_tags.append(f"#{clean}")
                    # Also add to tags metadata (without #)
                    if len(clean) < 50 and current_tag_len + len(clean) + 1 <= 400:
                        safe_tags.append(clean)
                        current_tag_len += len(clean) + 1
            if formatted_tags:
                hashtag_str = "\n\n" + " ".join(formatted_tags[:30])

        full_description = (description or "") + hashtag_str

        body = {
            'snippet': {
                'title': safe_title,
                'description': full_description,
                'tags': safe_tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }

        media = MediaFileUpload(
            file_path, 
            mimetype='video/mp4', 
            resumable=True
        )

        try:
            request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Upload Progress: {int(status.progress() * 100)}%")
            
            logger.info(f"Upload Successful! Video ID: {response.get('id')}")
            return response.get('id')
        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            return None

    @staticmethod
    def get_credentials_from_file():
        """Helper for OAuth2 flow (local/manual first run)."""
        # Note: If client_secret.json is 'web' type, we need to handle redirect_uris
        flow = InstalledAppFlow.from_client_secrets_file(
            settings.YOUTUBE_CLIENT_SECRET_FILE, 
            settings.YOUTUBE_SCOPES
        )
        # Use a fixed port if possible or let it choose
        creds = flow.run_local_server(port=8080, prompt='consent')
        return creds

    async def save_credentials(self, channel_id, user_id):
        """Save refreshed credentials back to the database."""
        if not self.credentials:
            return
            
        token_data = json.loads(self.credentials.to_json())
        async with Database.get_session() as session:
            from core.models import Channel
            await session.execute(
                update(Channel)
                .where(Channel.channel_id == channel_id)
                .values(oauth_tokens=token_data)
            )
            await session.commit()
            logger.info(f"Updated tokens for channel {channel_id} in database")
