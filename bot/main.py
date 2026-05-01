import os
import logging
import asyncio
import signal
import traceback
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from telegram import Bot, BotCommand, MenuButtonCommands, Update
from bot.handlers import (
    start_command, status_command, generate_command,
    schedule_command, view_schedule_command, cancel_command, button_callback
)
from core.config import settings
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Global application reference
_application = None


# ─────────────────────────── Health Check ────────────────────────────

@app.get("/")
@app.head("/")
async def health_check():
    return {"status": "online", "bot": "running", "mode": "webhook"}


# ─────────────────────────── Webhook Endpoint ─────────────────────────

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Receive updates from Telegram and dispatch to handlers."""
    global _application
    if _application is None:
        return Response(status_code=503)
    try:
        data = await request.json()
        update = Update.de_json(data, _application.bot)
        await _application.process_update(update)
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        logger.error(traceback.format_exc())
    return Response(status_code=200)


# ─────────────────────────── Bot Setup ────────────────────────────────

async def setup_bot_commands(bot):
    """Register bot commands and menu button."""
    commands = [
        BotCommand("start", "Start the bot and get welcome message"),
        BotCommand("generate", "Generate a new video now"),
        BotCommand("status", "Check recent job status"),
        BotCommand("schedule", "Set daily posting time (UTC)"),
        BotCommand("view_schedule", "View active schedules"),
        BotCommand("cancel", "Cancel current process")
    ]
    logger.info("Deleting old bot commands...")
    await bot.delete_my_commands()
    logger.info("Setting new bot commands...")
    await bot.set_my_commands(commands)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    registered = await bot.get_my_commands()
    logger.info(f"Verified {len(registered)} commands registered: {[c.command for c in registered]}")
    logger.info("=== MENU CONFIGURED SUCCESSFULLY ===")


async def init_services(application):
    """Initialize database and scheduler (non-fatal if they fail)."""
    try:
        from core.database import init_db
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
        logger.error(f"Scheduler stop error: {e}")
    try:
        from core.database import Database
        await Database.close()
    except Exception as e:
        logger.error(f"Database close error: {e}")
    logger.info("Bot post-stop completed")


async def run_bot():
    global _application

    application = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .post_stop(post_stop)
        .updater(None)      # ← Disable polling updater; we use webhook
        .build()
    )
    _application = application

    # Register handlers
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('generate', generate_command))
    application.add_handler(CommandHandler('schedule', schedule_command))
    application.add_handler(CommandHandler('view_schedule', view_schedule_command))
    application.add_handler(CommandHandler('cancel', cancel_command))
    application.add_handler(CallbackQueryHandler(button_callback))

    async with application:
        await setup_bot_commands(application.bot)
        await init_services(application)
        await application.start()

        # ── Set webhook URL on Telegram ──────────────────────────────
        # HF Spaces sets SPACE_HOST automatically, e.g. "username-spacename.hf.space"
        space_host = os.environ.get("SPACE_HOST", "")
        webhook_url = os.environ.get("WEBHOOK_URL", "")

        if not webhook_url and space_host:
            webhook_url = f"https://{space_host}/webhook"

        if webhook_url:
            await application.bot.set_webhook(
                url=webhook_url,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True
            )
            logger.info(f"=== WEBHOOK SET: {webhook_url} ===")
        else:
            logger.warning("No webhook URL configured — bot will not receive updates!")
            logger.warning("Set WEBHOOK_URL or deploy to Hugging Face Spaces (SPACE_HOST is auto-set).")

        logger.info("=== BOT IS NOW RUNNING IN WEBHOOK MODE! ===")

        # Keep running forever until killed
        await asyncio.Event().wait()


async def main():
    # HF Spaces requires port 7860. Falls back to PORT env var, then 7860.
    port = int(os.environ.get("PORT", os.environ.get("HF_PORT", 7860)))
    logger.info(f"Starting web server on port {port}...")

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(server.shutdown()))
        except NotImplementedError:
            logger.warning(f"Signal handler for {sig} not supported")

    await asyncio.gather(
        server.serve(),
        run_bot()
    )


if __name__ == '__main__':
    asyncio.run(main())
