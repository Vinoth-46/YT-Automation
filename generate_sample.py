import asyncio
import sys
import logging
from core.database import Database
from core.orchestrator import Orchestrator

# Set up logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing database...")
    Database.connect()
    
    # ── Custom Topic to trigger animations ───────────────────────────────────
    custom_topic = "Concrete Mix Ratio 1:2:4 vs 1:1.5:3"
    logger.info(f"Creating job for topic: '{custom_topic}'...")
    
    orchestrator = Orchestrator()
    job_id = await orchestrator.create_job(custom_topic=custom_topic)
    logger.info(f"Created Job ID: {job_id}")
    
    # Progress callback to show stage completion
    async def progress_callback(text):
        print(f"\n>>> PROGRESS UPDATE: {text}\n", flush=True)

    logger.info("Starting pipeline execution...")
    try:
        success = await orchestrator.run_pipeline(job_id, progress_callback=progress_callback)
        if success:
            logger.info("=== Video Generation Completed Successfully ===")
            
            # Fetch final video path from database
            from core.models import VideoAsset
            from sqlalchemy import select
            async with Database.get_session() as session:
                res = await session.execute(
                    select(VideoAsset).where(VideoAsset.job_id == job_id).order_by(VideoAsset.id.desc()).limit(1)
                )
                video_asset = res.scalar_one_or_none()
                if video_asset:
                    print(f"\nSUCCESS! Generated Video: {video_asset.draft_path}\n", flush=True)
                else:
                    print("\n⚠️ Video rendered, but VideoAsset not found in database!\n", flush=True)
        else:
            logger.error("Job execution failed.")
    except Exception as e:
        logger.error(f"Critical error during generation: {e}", exc_info=True)
    finally:
        logger.info("Closing database connection...")
        await Database.close()

if __name__ == "__main__":
    asyncio.run(main())
