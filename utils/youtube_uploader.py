import os
import pickle
import logging
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from core.config import settings

logger = logging.getLogger(__name__)

# Scopes for YouTube Data API v3
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

class YouTubeUploader:
    def __init__(self):
        self.credentials_path = os.path.join(settings.BASE_DIR, 'credentials', 'oauth_client_secret.json')
        self.token_path = os.path.join(settings.BASE_DIR, 'credentials', 'token.pickle')
        self.youtube = self._get_authenticated_service()

    def _get_authenticated_service(self):
        """Handle OAuth2 flow and return YouTube service object."""
        creds = None
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)
        
        # If no valid credentials, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    logger.error(f"Missing {self.credentials_path}. Please download it from Google Cloud Console.")
                    return None
                
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                # Note: run_local_server requires a browser. For a headless server, 
                # we'd need a different flow, but for MVP local setup is easier.
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for next time
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)

        return build('youtube', 'v3', credentials=creds)

    async def upload_video(self, video_path, title, description, tags=None, category_id="27"):
        """Upload video to YouTube."""
        if not self.youtube:
            return None

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or [],
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': 'private', # Default to private for safety/audit reasons
                'selfDeclaredMadeForKids': False
            }
        }

        try:
            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
            request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Uploading... {int(status.progress() * 100)}%")
            
            video_id = response.get('id')
            logger.info(f"Video uploaded successfully! ID: {video_id}")
            return video_id

        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            return None
