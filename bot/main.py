import os
import logging
import asyncio
import signal
import traceback
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from bot.handlers import (
    start_command, status_command, generate_command, 
    schedule_command, view_schedule_command, clear_schedule_command, 
    autopost_command, cancel_command, button_callback
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

# ── Security: Redact bot token from httpx logs ──────────────────────────────
class _TokenRedactFilter(logging.Filter):
    """Replace the Telegram bot token in log messages with [REDACTED]."""
    def __init__(self, token: str):
        super().__init__()
        self._token = token

    def filter(self, record: logging.LogRecord) -> bool:
        if self._token and self._token in record.getMessage():
            record.msg = record.msg.replace(self._token, "bot[REDACTED]")
            record.args = ()
        return True

def _apply_token_filter():
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            from core.config import settings
            token = settings.TELEGRAM_BOT_TOKEN or ""
        if token:
            _f = _TokenRedactFilter(token)
            logging.getLogger("httpx").addFilter(_f)
            logging.getLogger("telegram").addFilter(_f)
    except Exception:
        pass

_apply_token_filter()
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI()

# Global reference  shutdown
_application = None
_shutdown_event = asyncio.Event()

@app.get("/")
@app.head("/")
async def health_check():
    return {"status": "online", "bot": "running"}

async def setup_bot_commands(bot):
    """Register bot commands and menu button."""
    commands = [
        BotCommand("start", "Start the bot and get welcome message"),
        BotCommand("generate", "Generate a new video now"),
        BotCommand("status", "Check recent job status"),
        BotCommand("schedule", "Set daily posting time (UTC)"),
        BotCommand("view_schedule", "View active schedules"),
        BotCommand("clearschedule", "Revoke/Clear all active schedules"),
        BotCommand("autopost", "Toggle auto-approval mode (on/off)"),
        BotCommand("cancel", "Cancel current process")
    ]
    
    logger.info("Deleting old bot commands...")
    await bot.delete_my_commands()
    
    logger.info("Setting new bot commands...")
    result = await bot.set_my_commands(commands)
    
    logger.info("Setting menu button to MenuButtonCommands...")
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    
    registered = await bot.get_my_commands()
    logger.info(f"Verified {len(registered)} commands registered: {[c.command for c in registered]}")
    logger.info("=== MENU CONFIGURED SUCCESSFULLY ===")

async def init_services(application):
    """Initialize database and scheduler (non-fatal if they fail)."""
    try:
        from core.database import Database, init_db
        await init_db()
        logger.info("=== DATABASE INITIALIZED ===")
    except Exception as e:
        logger.error(f"=== DATABASE FAILED (non-fatal): {e} ===")
        logger.error(traceback.format_exc())

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
        pass
    
    try:
        from core.database import Database
        await Database.close()
    except Exception as e:
        pass
    
    logger.info("Bot post-stop completed")

async def run_bot():
    global _application
    
    # Clear any stale getUpdates session
    logger.info("🧹 Clearing stale Telegram sessions...")
    try:
        temp_bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        async with temp_bot:
            await temp_bot.delete_webhook(drop_pending_updates=True)
            me = await temp_bot.get_me()
            logger.info(f"✅ Bot Identity: @{me.username} ({me.first_name})")
        logger.info("=== STALE SESSIONS CLEARED. WAITING FOR RELEASE... ===")
    except Exception as e:
        logger.warning(f"⚠️ Session clear warning: {e}")
    
    # Wait longer to allow Telegram to release the session from other instances
    await asyncio.sleep(5)
    
    application = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .pool_timeout(900.0)
        .connect_timeout(900.0)
        .read_timeout(900.0)
        .write_timeout(900.0)
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
    application.add_handler(CommandHandler('clearschedule', clear_schedule_command))
    application.add_handler(CommandHandler('autopost', autopost_command))
    application.add_handler(CommandHandler('cancel', cancel_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("Bot is starting...")
    async with application:
        await setup_bot_commands(application.bot)
        await init_services(application)
        
        await application.start()
        await application.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
        )
        logger.info("=== BOT IS NOW POLLING FOR MESSAGES! ===")
        await _shutdown_event.wait()
        logger.info("=== STOPPING BOT POLLING ===")
        await application.updater.stop()
        await application.stop()

async def main():
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: _shutdown_event.set())
        except NotImplementedError:
            pass
    
    await asyncio.gather(
        server.serve(),
        run_bot()
    )

if __name__ == '__main__':
    asyncio.run(main())
