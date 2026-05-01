import asyncio
import os
import sys
import json
import logging

# Add project root to path
sys.path.append(os.getcwd())

from core.database import Database
from core.models import Channel, User
from sqlalchemy import select
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    token_file = 'credentials/youtube_token.json'
    
    if not os.path.exists(token_file):
        print(f"❌ Error: {token_file} not found!")
        return

    try:
        # 1. Read existing token
        with open(token_file, 'r') as f:
            token_data = json.load(f)
        
        creds = Credentials.from_authorized_user_info(token_data)
        
        # 2. Get Channel Info from YouTube
        print("Connecting to YouTube to verify token...")
        youtube = build("youtube", "v3", credentials=creds)
        channels_resp = youtube.channels().list(part="id,snippet", mine=True).execute()
        
        if not channels_resp.get("items"):
            print("❌ Error: No YouTube channel found for this token.")
            return

        yt_channel = channels_resp["items"][0]
        yt_id = yt_channel["id"]
        yt_title = yt_channel["snippet"]["title"]
        print(f"Found Channel: {yt_title} ({yt_id})")

        # 3. Save to Database
        Database.connect()
        async with Database.get_session() as session:
            # Get or create default user
            res_u = await session.execute(select(User).limit(1))
            user = res_u.scalar_one_or_none()
            if not user:
                user = User(telegram_id=0)
                session.add(user)
                await session.commit()
                await session.refresh(user)

            # Update or Create Channel
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
            print(f"✅ Success! YouTube tokens for '{yt_title}' saved to the database.")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await Database.close()

if __name__ == "__main__":
    asyncio.run(main())
