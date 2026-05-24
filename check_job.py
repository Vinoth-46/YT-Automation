import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from core.models import ScriptAsset
from core.config import settings

async def check_job_18():
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
        
    engine = create_async_engine(settings.POSTGRES_URL)
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with SessionLocal() as session:
        result = await session.execute(select(ScriptAsset).where(ScriptAsset.job_id == 18))
        script = result.scalar_one_or_none()
        if script:
            print(f"Title: {script.title}")
            print(f"Description: {script.description}")
            print(f"Script Text:\n{script.script_text}")
            print(f"Similarity Score: {script.similarity_score}")
        else:
            # Let's find the latest script asset instead
            res = await session.execute(select(ScriptAsset).order_by(ScriptAsset.id.desc()).limit(1))
            latest = res.scalar_one_or_none()
            if latest:
                print(f"LATEST JOB ID: {latest.job_id}")
                print(f"Title: {latest.title}")
                print(f"Topic: {latest.topic}")
                print(f"Thumbnail Text: {latest.thumbnail_text}")
                
                # Fetch scenes and print
                import json
                try:
                    # Let's see if we have JSON data or if it's stored differently
                    print(f"Script Text:\n{latest.script_text}")
                except Exception as je:
                    print(f"Error printing script: {je}")
            else:
                print("No scripts found in database!")

if __name__ == "__main__":
    asyncio.run(check_job_18())
