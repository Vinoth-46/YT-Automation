import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from core.models import Job

async def check():
    engine = create_async_engine('postgresql+asyncpg://user:password@localhost/yt_automation')
    session = async_sessionmaker(engine, class_=AsyncSession)()
    result = await session.execute(select(Job.id, Job.state, Job.planned_date).order_by(Job.id.desc()).limit(40))
    jobs = result.all()
    print('Total in last 40:', len(jobs))
    for j in jobs:
        print(j)
    await session.close()
    await engine.dispose()

asyncio.run(check())
