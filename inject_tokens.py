import asyncio
import json
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from core.models import Channel, Base
from core.config import settings

async def inject_tokens():
    engine = create_async_engine(settings.POSTGRES_URL)
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    with open("credentials/youtube_token.json", "r") as f:
        token_data = json.load(f)
        
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with SessionLocal() as session:
        # Check if channel exists
        result = await session.execute(text("SELECT id FROM channels LIMIT 1"))
        channel_exists = result.scalar_one_or_none()
        
        if channel_exists:
            await session.execute(
                text("UPDATE channels SET oauth_tokens = :tokens"),
                {"tokens": json.dumps(token_data)}
            )
            print("Updated existing channel with tokens.")
        else:
            new_channel = Channel(
                channel_id="UC_YOUR_CHANNEL", # dummy id
                user_id=1,
                oauth_tokens=token_data
            )
            session.add(new_channel)
            print("Inserted new channel with tokens.")
            
        await session.commit()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(inject_tokens())
