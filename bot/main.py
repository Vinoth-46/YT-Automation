import logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from bot.handlers import start_command, status_command, button_callback
from core.config import settings
from core.database import Database

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def post_init(application):
    """Run after bot initialization."""
    await Database.connect()

async def post_stop(application):
    """Run before bot shutdown."""
    await Database.close()

if __name__ == '__main__':
    application = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).post_init(post_init).post_stop(post_stop).build()
    
    # Handlers
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("Bot is starting...")
    application.run_polling()
