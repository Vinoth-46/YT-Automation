import asyncio
from core.database import init_db
from core.orchestrator import Orchestrator

async def test_publish():
    await init_db()
    orch = Orchestrator()
    # Try to publish Job 14
    await orch.publish_video(14)

if __name__ == "__main__":
    asyncio.run(test_publish())
