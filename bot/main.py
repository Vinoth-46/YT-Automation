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
from telegram import Bot, BotCommand, MenuButtonCommands

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

async def setup_bot_commands(bot):
    """Register bot commands and menu button. Called directly on the bot object."""
    commands = [
        BotCommand("start", "Start the bot and get welcome message"),
        BotCommand("generate", "Generate a new video now"),
        BotCommand("status", "Check recent job status"),
        BotCommand("schedule", "Set daily posting time (UTC)"),
        BotCommand("view_schedule", "View active schedules"),
        BotCommand("cancel", "Cancel current process")
    ]
    
    # Step 1: Delete old commands first to force refresh
    logger.info("Deleting old bot commands...")
    await bot.delete_my_commands()
    logger.info("Old commands deleted.")
    
    # Step 2: Set new commands
    logger.info("Setting new bot commands...")
    result = await bot.set_my_commands(commands)
    logger.info(f"set_my_commands returned: {result}")
    
    # Step 3: Explicitly set the menu button to show commands list
    logger.info("Setting menu button to MenuButtonCommands...")
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    logger.info("Menu button set to commands mode.")
    
    # Step 4: Verify commands were set
    registered = await bot.get_my_commands()
    logger.info(f"Verified {len(registered)} commands registered: {[c.command for c in registered]}")

async def init_services(application):
    """Initialize database and scheduler (non-fatal if they fail)."""
    # Initialize database
    try:
        from core.database import Database, init_db
        await init_db()
        logger.info("=== DATABASE INITIALIZED ===")
    except Exception as e:
        logger.error(f"=== DATABASE FAILED (non-fatal): {e} ===")
        logger.error(traceback.format_exc())

    # Start scheduler
    try:
        from core.scheduler import SchedulerService
        scheduler = SchedulerService()
        await scheduler.load_schedules()
        scheduler.start()
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
        # Register commands BEFORE starting - this runs with the bot fully initialized
        try:
            await setup_bot_commands(application.bot)
            logger.info("=== MENU CONFIGURED SUCCESSFULLY ===")
        except Exception as e:
            logger.error(f"=== MENU SETUP FAILED: {e} ===")
            logger.error(traceback.format_exc())
        
        # Initialize DB and scheduler (non-fatal)
        await init_services(application)
        
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
            logger.warning(f"Signal handler for {sig} not supported on this platform")
    
    await asyncio.gather(
        server.serve(),
        run_bot()
    )

if __name__ == '__main__':
    asyncio.run(main())
