import os
import threading
import asyncio
import logging
import time
import shutil
import psutil
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse

# Import configuration and pipeline
import config
from scripts.telegram_bot import ProductionBot

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("server")

app = FastAPI(title="YouTube Automation Server")

# Global bot instance
bot_instance = None
bot_thread = None

def cleanup_temp_files():
    """Wipe output and data temp folders on startup to clear corrupted files."""
    logger.info("🧹 Cleaning up temporary files...")
    # List of directories to clean. Using try/except for each to avoid stopping on one error.
    dirs_to_clean = [config.OUTPUT_DIR, config.LOGS_DIR]
    for d in dirs_to_clean:
        if d.exists():
            try:
                for item in d.iterdir():
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                logger.info(f"✅ Cleaned {d}")
            except Exception as e:
                logger.error(f"❌ Failed to clean {d}: {e}")

def run_bot_polling():
    """Function to run the Telegram bot in polling mode."""
    global bot_instance
    try:
        logger.info("🤖 Starting Telegram Bot polling...")
        bot_instance = ProductionBot()
        bot_instance.app.run_polling(close_loop=False)
    except Exception as e:
        logger.error(f"❌ Bot Thread Crashed: {e}")

@app.on_event("startup")
async def startup_event():
    global bot_thread
    
    # 1. Cleanup
    cleanup_temp_files()
    
    # 2. Start Bot in Background Thread
    bot_thread = threading.Thread(target=run_bot_polling, daemon=True)
    bot_thread.start()
    logger.info("🚀 Server startup complete.")

@app.get("/")
async def root():
    return {
        "message": "YouTube Automation Server is running",
        "platform": "Hugging Face Spaces / Server",
        "bot_status": "Online" if (bot_thread and bot_thread.is_alive()) else "Offline"
    }

@app.get("/health")
async def health_check():
    """Detailed health check for monitoring/watchdogs."""
    bot_alive = bot_thread and bot_thread.is_alive()
    
    # Check system resources
    ram = psutil.virtual_memory()
    
    status = "ok" if bot_alive else "degraded"
    
    return JSONResponse(
        status_code=200 if status == "ok" else 503,
        content={
            "status": status,
            "bot_alive": bot_alive,
            "memory_usage_percent": ram.percent,
            "available_memory_mb": ram.available / (1024 * 1024),
            "uptime_seconds": time.monotonic()
        }
    )

@app.get("/render_lock/status")
async def get_lock_status():
    """Check if a render is currently in progress."""
    return {"locked": config.RENDER_LOCK.locked()}

if __name__ == "__main__":
    import uvicorn
    # Use port from environment variable (standard for HF/Render)
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
