import asyncio
import os
import sys
import json
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.youtube_engine import YouTubeEngine
from core.database import Database
from core.models import Channel, User
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    print("=== YouTube Authentication Helper ===")
    print("This script will open a browser to authenticate your YouTube channel.")
    
    try:
        # 1. Run the OAuth flow
        # Note: This requires client_secret.json in the credentials folder
        creds = YouTubeEngine.get_credentials_from_file()
        token_data = json.loads(creds.to_json())
        
        # 2. Connect to Database
        Database.connect()
        async with Database.get_session() as session:
            # Get the first user or create one
            res_u = await session.execute(select(User).limit(1))
            user = res_u.scalar_one_or_none()
            if not user:
                print("No user found in database. Creating a default user...")
                user = User(telegram_id=0) # Placeholder
                session.add(user)
                await session.commit()
                await session.refresh(user)

            # Check if channel exists
            # We'll use a placeholder 'primary' channel ID for now if we don't know it
            # In a real app, you'd get this from the YouTube API response
            from googleapiclient.discovery import build
            youtube = build("youtube", "v3", credentials=creds)
            channels_resp = youtube.channels().list(part="id,snippet", mine=True).execute()
            
            if not channels_resp.get("items"):
                print("Error: No YouTube channel found for this account.")
                return

            yt_channel = channels_resp["items"][0]
            yt_id = yt_channel["id"]
            yt_title = yt_channel["snippet"]["title"]
            
            print(f"Authenticated as: {yt_title} ({yt_id})")
            
            res_c = await session.execute(select(Channel).where(Channel.channel_id == yt_id))
            db_channel = res_c.scalar_one_or_none()
            
            if not db_channel:
                db_channel = Channel(
                    user_id=user.id,
                    channel_id=yt_id,
                    oauth_tokens=token_data
                )
                session.add(db_channel)
            else:
                db_channel.oauth_tokens = token_data
            
            await session.commit()
            print("Success! YouTube tokens saved to the database.")
            print("You can now close this script and use the bot.")

    except Exception as e:
        print(f"Error during authentication: {e}")
    finally:
        await Database.close()

if __name__ == "__main__":
    asyncio.run(main())
