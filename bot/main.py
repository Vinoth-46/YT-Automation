import logging
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from bot.handlers import start_command, status_command, generate_command, schedule_command, button_callback
from core.config import settings
from core.database import Database, init_db
from core.scheduler import SchedulerService

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

scheduler_service = SchedulerService()

async def post_init(application):
    """Run after bot initialization."""
    await init_db()
    await scheduler_service.load_schedules()
    scheduler_service.start()
    logging.info("Bot post-init completed")

async def post_stop(application):
    """Run before bot shutdown."""
    scheduler_service.stop()
    await Database.close()
    logging.info("Bot post-stop completed")

if __name__ == '__main__':
    application = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).post_init(post_init).post_stop(post_stop).build()
    
    # Handlers
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('generate', generate_command))
    application.add_handler(CommandHandler('schedule', schedule_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("Bot is starting...")
    application.run_polling()
