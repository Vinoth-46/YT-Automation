import asyncio
import os
import sys
import logging

# Ensure absolute imports work from the repository root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import init_db
from core.orchestrator import Orchestrator
from core.config import settings

# Force the video engine to use YouTube search and download
settings.VIDEO_SOURCE = "youtube"

# Set up clean logging to stdout so we can watch the progress live
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

async def main():
    logger = logging.getLogger("test_generate_youtube")
    logger.info("Initializing database connection...")
    await init_db()
    
    orch = Orchestrator()
    
    # We choose a highly specific, interesting Indian civil engineering topic
    topic = "Why red clay bricks are still popular in Tamil Nadu vs hollow concrete blocks"
    logger.info(f"Creating test job for topic: '{topic}'")
    job_id = await orch.create_job(custom_topic=topic)
    logger.info(f"Created Job #{job_id}. Running the full automation pipeline...")
    
    try:
        # Run the full pipeline (Script Gen -> Audio Gen -> Video Gen (with YouTube Downloader))
        await orch.run_pipeline(job_id)
        logger.info(f"🎉 Success! Pipeline completed for Job #{job_id}!")
    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
