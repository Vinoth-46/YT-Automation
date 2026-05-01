import os
import logging
import asyncio
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
from telegram import BotCommand

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

scheduler_service = SchedulerService()
app = FastAPI()

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

async def run_bot():
    application = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )
    
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
        await application.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is now polling for messages!")
        # Keep the bot running
        await asyncio.Event().wait()

async def main():
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    
    await asyncio.gather(
        server.serve(),
        run_bot()
    )

if __name__ == '__main__':
    asyncio.run(main())
