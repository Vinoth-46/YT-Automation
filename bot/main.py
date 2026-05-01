import logging
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from bot.handlers import start_command, status_command, generate_command, schedule_command, button_callback
from core.config import settings
from core.database import Database, init_db
from core.scheduler import SchedulerService
import uvicorn
from fastapi import FastAPI

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

scheduler_service = SchedulerService()
app = FastAPI()

@app.get("/")
@app.head("/")
async def health_check():
    return {"status": "online", "bot": "running"}

async def post_init(application):
    """Run after bot initialization."""
    try:
        await init_db()
        await scheduler_service.load_schedules()
        scheduler_service.start()
        logging.info("Bot post-init completed")
    except Exception as e:
        logging.error(f"Post-init error: {e}")

async def post_stop(application):
    """Run before bot shutdown."""
    scheduler_service.stop()
    await Database.close()
    logging.info("Bot post-stop completed")

async def run_bot():
    application = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).post_init(post_init).post_stop(post_stop).build()
    
    # Handlers
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('generate', generate_command))
    application.add_handler(CommandHandler('schedule', schedule_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logging.info("Bot is starting polling...")
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        # Keep the bot running without a busy loop
        await asyncio.Event().wait()


async def main():
    # Run both the health check server and the Telegram bot
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    
    await asyncio.gather(
        server.serve(),
        run_bot()
    )

if __name__ == '__main__':
    import os
    asyncio.run(main())

