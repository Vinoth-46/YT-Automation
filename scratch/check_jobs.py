import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from core.models import Job
from core.config import settings

async def check():
    engine = create_async_engine(settings.POSTGRES_URL)
    session = async_sessionmaker(engine, class_=AsyncSession)()
    result = await session.execute(select(Job.id, Job.state, Job.failed_stage, Job.error_message, Job.planned_date).order_by(Job.id.desc()).limit(10))
    jobs = result.all()
    print('Total in last 10:', len(jobs))
    for j in jobs:
        print(f"ID: {j[0]} | State: {j[1]} | Failed Stage: {j[2]} | Error: {j[3]} | Date: {j[4]}")
    await session.close()
    await engine.dispose()

asyncio.run(check())
