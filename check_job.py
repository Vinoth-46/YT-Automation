import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from core.models import ScriptAsset
from core.config import settings

async def check_job_18():
    engine = create_async_engine(settings.POSTGRES_URL)
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as session:
        result = await session.execute(select(ScriptAsset).where(ScriptAsset.job_id == 18))
        script = result.scalar_one_or_none()
        if script:
            print(f"Title ({len(script.title)} chars)")
            print(f"Description ({len(script.description)} chars)")
            
            tags_str = ",".join(script.hashtags) if script.hashtags else ""
            print(f"Tags ({len(tags_str)} chars)")
        else:
            print("Job 18 script not found!")

if __name__ == "__main__":
    asyncio.run(check_job_18())
