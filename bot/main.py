import os
import logging
import asyncio
import signal
import traceback
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from bot.handlers import (
    start_command, status_command, generate_command, 
    schedule_command, view_schedule_command, cancel_command, button_callback
)
from core.config import settings
import uvicorn
from fastapi import FastAPI
from telegram import Bot, BotCommand

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
        logger.error(traceback.format_exc())

    # Step 2: Initialize database (non-fatal)
    try:
        from core.database import Database, init_db
        await init_db()
        logger.info("=== DATABASE INITIALIZED ===")
    except Exception as e:
        logger.error(f"=== DATABASE FAILED (non-fatal): {e} ===")
        logger.error(traceback.format_exc())

    # Step 3: Start scheduler (non-fatal)
    try:
        from core.scheduler import SchedulerService
        scheduler = SchedulerService()
        await scheduler.load_schedules()
        scheduler.start()
        # Store on the application for later cleanup
        application.bot_data["scheduler"] = scheduler
        logger.info("=== SCHEDULER STARTED ===")
    except Exception as e:
        logger.error(f"=== SCHEDULER FAILED (non-fatal): {e} ===")
        logger.error(traceback.format_exc())

async def post_stop(application):
    """Run before bot shutdown."""
    try:
        scheduler = application.bot_data.get("scheduler")
        if scheduler:
            scheduler.stop()
    except Exception as e:
        logger.error(f"Scheduler stop error: {e}")
    
    try:
        from core.database import Database
        await Database.close()
    except Exception as e:
        logger.error(f"Database close error: {e}")
    
    logger.info("Bot post-stop completed")

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
    await asyncio.sleep(3)
    
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
        logger.info("=== BOT IS NOW POLLING FOR MESSAGES! ===")
        # Wait until shutdown is signaled
        await _shutdown_event.wait()
        # Gracefully stop within the context manager
        logger.info("=== STOPPING BOT POLLING ===")
        await application.updater.stop()
        await application.stop()

async def main():
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    
    # Wire up SIGTERM/SIGINT for graceful shutdown (Render sends SIGTERM)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig,
                lambda: _shutdown_event.set()
            )
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            logger.warning(f"Signal handler for {sig} not supported on this platform")
    
    await asyncio.gather(
        server.serve(),
        run_bot()
    )

if __name__ == '__main__':
    asyncio.run(main())
