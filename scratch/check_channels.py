import asyncio
import sys
import os

# Add the current directory to sys.path to allow imports
sys.path.append(os.getcwd())

from core.database import Database
from core.models import Channel
from sqlalchemy import select

async def check():
    try:
        # Connect to DB
        Database.connect()
        async with Database.get_session() as session:
            result = await session.execute(select(Channel))
            channels = result.scalars().all()
            print(f"Total Channels: {len(channels)}")
            for c in channels:
                print(f"Channel ID: {c.channel_id}")
                print(f"Has tokens: {c.oauth_tokens is not None}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await Database.close()

if __name__ == "__main__":
    asyncio.run(check())
