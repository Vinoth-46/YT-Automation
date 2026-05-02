import asyncio
from core.models import Channel
from core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from engines.youtube_engine import YouTubeEngine

async def test_auth():
    engine = create_async_engine(settings.POSTGRES_URL)
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as session:
        result = await session.execute(select(Channel).limit(1))
        channel = result.scalar_one_or_none()
        
        try:
            yt = YouTubeEngine(token_data=channel.oauth_tokens)
            print("Auth successful!")
            # Save the refreshed tokens back!
            await yt.save_credentials(channel.channel_id, channel.user_id)
            print("Saved refreshed credentials!")
        except Exception as e:
            print(f"Exception during auth: {e}")

if __name__ == "__main__":
    asyncio.run(test_auth())
