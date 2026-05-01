import os
import logging
import asyncio
import signal
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from bot.handlers import (
    start_command, status_command, generate_command, 
    schedule_command, view_schedule_command, cancel_command, button_callback
)
from core.config import settings
from core.database import Database, init_db
from core.scheduler import SchedulerService
import uvicorn
from fastapi import FastAPI
from telegram import Bot, BotCommand

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

scheduler_service = SchedulerService()
app = FastAPI()

# Global reference for graceful shutdown
_application = None
_shutdown_event = asyncio.Event()

@app.get("/")
@app.head("/")
async def health_check():
    return {"status": "online", "bot": "running"}

async def post_init(application):
    """Run after bot initialization."""
    # Step 1: Always set up the command menu (no DB needed)
    try:
        commands = [
            BotCommand("start", "Start the bot and get welcome message"),
            BotCommand("generate", "Generate a new video now"),
            BotCommand("status", "Check recent job status"),
            BotCommand("schedule", "Set daily posting time (UTC)"),
            BotCommand("view_schedule", "View active schedules"),
            BotCommand("cancel", "Cancel current process")
        ]
        await application.bot.set_my_commands(commands)
        logger.info("=== MENU CONFIGURED SUCCESSFULLY ===")
    except Exception as e:
        logger.error(f"=== MENU FAILED: {e} ===")

    # Step 2: Initialize database
    try:
        await init_db()
        logger.info("=== DATABASE INITIALIZED ===")
    except Exception as e:
        logger.error(f"=== DATABASE FAILED: {e} ===")

    # Step 3: Start scheduler
    try:
        await scheduler_service.load_schedules()
        scheduler_service.start()
        logger.info("=== SCHEDULER STARTED ===")
    except Exception as e:
        logger.error(f"=== SCHEDULER FAILED: {e} ===")

async def post_stop(application):
    """Run before bot shutdown."""
    scheduler_service.stop()
    await Database.close()
    logger.info("Bot post-stop completed")

async def graceful_shutdown():
    """Gracefully stop the bot and polling."""
    global _application
    logger.info("=== GRACEFUL SHUTDOWN INITIATED ===")
    if _application:
        try:
            await _application.updater.stop()
            await _application.stop()
            await _application.shutdown()
            logger.info("=== BOT STOPPED CLEANLY ===")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    _shutdown_event.set()

async def run_bot():
    global _application
    
    # Clear any stale getUpdates session from a previous instance
    logger.info("Clearing stale Telegram sessions...")
    try:
        temp_bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        async with temp_bot:
            await temp_bot.delete_webhook(drop_pending_updates=True)
        logger.info("=== STALE SESSIONS CLEARED ===")
    except Exception as e:
        logger.warning(f"Could not clear stale sessions: {e}")
    
    # Small delay to let any previous instance fully release the getUpdates lock
    await asyncio.sleep(2)
    
    application = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )
    _application = application
    
    # Handlers
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('generate', generate_command))
    application.add_handler(CommandHandler('schedule', schedule_command))
    application.add_handler(CommandHandler('view_schedule', view_schedule_command))
    application.add_handler(CommandHandler('cancel', cancel_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("Bot is starting...")
    async with application:
        await application.start()
        await application.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
        )
        logger.info("Bot is now polling for messages!")
        # Wait until shutdown is signaled
        await _shutdown_event.wait()

async def main():
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    
    # Wire up SIGTERM/SIGINT for graceful shutdown (Render sends SIGTERM)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(graceful_shutdown())
        )
    
    await asyncio.gather(
        server.serve(),
        run_bot()
    )

if __name__ == '__main__':
    asyncio.run(main())
