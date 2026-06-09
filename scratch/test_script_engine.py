import asyncio
import os
import sys
import logging

# Ensure absolute imports work from the repository root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import init_db
from engines.script_engine import ScriptEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_script_engine")

async def main():
    await init_db()
    engine = ScriptEngine()
    
    topic = "Why red clay bricks are still popular in Tamil Nadu vs hollow concrete blocks"
    logger.info(f"Testing content generation for topic: '{topic}'")
    
    result = await engine.generate_full_content(custom_topic=topic)
    if result:
        logger.info("🎉 SUCCESS! Content generated:")
        logger.info(f"Topic: {result.get('topic')}")
        logger.info(f"Script Narration Length: {len(result.get('script', {}).get('narration', ''))} chars")
        logger.info(f"Metadata Title: {result.get('script', {}).get('metadata', {}).get('title')}")
    else:
        logger.error("❌ FAILED to generate content.")

if __name__ == "__main__":
    asyncio.run(main())
