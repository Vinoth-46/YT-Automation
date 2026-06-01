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
            self.credentials = Credentials.from_authorized_user_info(token_data)
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

    def upload_video(self, file_path, title, description, tags=None, category_id="27", privacy_status="private", language="ta"):
        """Upload video to YouTube."""
        if not self.youtube:
            logger.error("YouTube client not initialized. Authenticate first.")
            return None

        # Sanitize and truncate title to YouTube's strict 100 character limit
        safe_title = title.replace("<", "").replace(">", "")
        if len(safe_title) > 95:
            safe_title = safe_title[:95] + "..."

        # Build visible hashtag string AND safe_tags (YouTube metadata)
        # YouTube only shows the FIRST 3 hashtags as clickable blue links above the title
        # So we put the 3 most important ones at the START of the description
        safe_tags = ["Shorts"]  # Always ensure #Shorts is first for Shorts shelf discovery
        top_hashtags = ["#Shorts"]  # First 3 go at TOP of description
        remaining_hashtags = []
        current_tag_len = len("Shorts") + 1
        if tags:
            for tag in tags:
                clean = tag.strip().lstrip("#").replace(" ", "")
                if clean and clean.lower() != "shorts":  # Skip duplicates of Shorts
                    if len(clean) < 50 and current_tag_len + len(clean) + 1 <= 400:
                        safe_tags.append(clean)
                        current_tag_len += len(clean) + 1
                    hashtag = f"#{clean}"
                    if len(top_hashtags) < 3:
                        top_hashtags.append(hashtag)
                    else:
                        remaining_hashtags.append(hashtag)
        
        # Top 3 hashtags go BEFORE description, remaining go AFTER
        top_hashtag_str = " ".join(top_hashtags)
        remaining_hashtag_str = "\n\n" + " ".join(remaining_hashtags[:25]) if remaining_hashtags else ""

        full_description = top_hashtag_str + "\n\n" + (description or "") + remaining_hashtag_str

        body = {
            'snippet': {
                'title': safe_title,
                'description': full_description,
                'tags': safe_tags,
                'categoryId': category_id,
                'defaultLanguage': language,
                'defaultAudioLanguage': language
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

    def upload_thumbnail(self, video_id, thumbnail_path):
        """Upload custom thumbnail to a YouTube video."""
        if not self.youtube:
            logger.error("YouTube client not initialized.")
            return False
            
        try:
            request = self.youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype='image/jpeg')
            )
            request.execute()
            logger.info(f"Thumbnail uploaded successfully for video {video_id}!")
            return True
        except Exception as e:
            logger.error(f"Failed to upload thumbnail: {e}")
            return False

    def post_comment(self, video_id, text):
        """Post a top-level comment on a video."""
        if not self.youtube:
            logger.error("YouTube client not initialized. Authenticate first.")
            return None
            
        try:
            request = self.youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": text
                            }
                        }
                    }
                }
            )
            response = request.execute()
            logger.info(f"Comment posted successfully! ID: {response.get('id')}")
            return response.get("id")
        except Exception as e:
            logger.error(f"Failed to post comment to video {video_id}: {e}")
            return None

    def upload_captions(self, video_id, srt_path, language="ta", name="Tamil Subtitles"):
        """Upload caption/subtitle track to an existing YouTube video."""
        if not self.youtube:
            logger.error("YouTube client not initialized.")
            return False
            
        try:
            logger.info(f"Uploading caption track {srt_path} to video {video_id}...")
            body = {
                "snippet": {
                    "videoId": video_id,
                    "language": language,
                    "name": name,
                    "isDraft": False
                }
            }
            media = MediaFileUpload(
                srt_path,
                mimetype="application/octet-stream",
                resumable=True
            )
            request = self.youtube.captions().insert(
                part="snippet",
                body=body,
                media_body=media
            )
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Caption Upload Progress: {int(status.progress() * 100)}%")
            logger.info(f"Caption uploaded successfully! Caption ID: {response.get('id')}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload caption: {e}")
            return False

    def set_video_localizations(self, video_id, localizations):
        """Set multi-language titles and descriptions for a video.
        
        Args:
            video_id: YouTube video ID
            localizations: dict of {language_code: {"title": "...", "description": "..."}}
                           e.g. {"en": {"title": "...", "description": "..."}, "ta": {...}}
        """
        if not self.youtube:
            logger.error("YouTube client not initialized.")
            return False
            
        try:
            # First fetch the current video snippet to preserve existing data
            video_response = self.youtube.videos().list(
                part="snippet,localizations",
                id=video_id
            ).execute()
            
            if not video_response.get("items"):
                logger.warning(f"Video {video_id} not found for localization update")
                return False
            
            video_data = video_response["items"][0]
            existing_localizations = video_data.get("localizations", {})
            existing_localizations.update(localizations)
            
            snippet = video_data["snippet"]
            # Ensure the snippet has a default language set so the YouTube API accepts localizations
            if not snippet.get("defaultLanguage"):
                snippet["defaultLanguage"] = "ta"
            
            # Update with merged localizations and snippet containing defaultLanguage
            self.youtube.videos().update(
                part="snippet,localizations",
                body={
                    "id": video_id,
                    "snippet": snippet,
                    "localizations": existing_localizations
                }
            ).execute()
            
            logger.info(f"Video localizations set for {list(localizations.keys())} on video {video_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set video localizations: {e}")
            return False

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
