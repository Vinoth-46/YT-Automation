import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from core.models import Channel
from core.config import settings
import json

async def check():
    engine = create_async_engine(settings.POSTGRES_URL)
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as session:
        result = await session.execute(select(Channel).limit(1))
        channel = result.scalar_one_or_none()
        if channel:
            print(f"Token type: {type(channel.oauth_tokens)}")
            print(f"Token value: {channel.oauth_tokens}")
            
            # If it's a string, fix it!
            if isinstance(channel.oauth_tokens, str):
                print("Fixing token...")
                channel.oauth_tokens = json.loads(channel.oauth_tokens)
                await session.commit()
                print("Fixed!")
        else:
            print("No channel found")

if __name__ == "__main__":
    asyncio.run(check())
