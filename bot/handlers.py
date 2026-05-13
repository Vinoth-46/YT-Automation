import os
import logging
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

logger = logging.getLogger(__name__)


# ── Authorization guard ──────────────────────────────────────────────────────
def _is_authorized(update: Update) -> bool:
    """Return True if the user OR the chat group is in the ALLOWED_CHAT_IDS list."""
    from core.config import settings
    user_id = str(update.effective_user.id) if update.effective_user else ""
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    return (int(user_id) in settings.ALLOWED_CHAT_IDS if user_id else False) or (int(chat_id) in settings.ALLOWED_CHAT_IDS if chat_id else False)

async def _reject_unauthorized(update: Update):
    """Reply with a rejection message for unauthorized users."""
    user = update.effective_user
    logger.warning(f"Unauthorized access attempt from user {user.id} (@{user.username})")
    if update.message:
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
    elif update.callback_query:
        await update.callback_query.answer("⛔ Unauthorized.", show_alert=True)
# ─────────────────────────────────────────────────────────────────────────────


def _get_db():
    """Lazy import Database to avoid import-time crashes."""
    from core.database import Database
    return Database


def _get_models():
    """Lazy import models."""
    from core.models import Job, JobState, Schedule, User, ScriptAsset, VideoAsset
    return Job, JobState, Schedule, User, ScriptAsset, VideoAsset


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return

    user = update.effective_user
    logger.info(f"Received /start command from user {user.id} ({user.first_name})")
    
    try:
        Database = _get_db()
        _, _, _, User, _, _ = _get_models()
        async with Database.get_session() as session:
            logger.info(f"Checking database for user {user.id}...")
            result = await session.execute(select(User).where(User.telegram_id == user.id))
            db_user = result.scalar_one_or_none()
            if not db_user:
                db_user = User(telegram_id=user.id, timezone="Asia/Kolkata")
                session.add(db_user)
                await session.commit()
            logger.info(f"Database check completed for user {user.id}")
    except Exception as e:
        logger.error(f"Database error in start_command: {e}")
        # We continue anyway to at least show the welcome message

    welcome_text = (
        f"வணக்கம் {user.first_name}! 👋\n\n"
        "Civil Engineering YouTube Autopilot-க்கு வரவேற்கிறோம்.\n\n"
        "Features:\n"
        "🚀 Instant Video Generation\n"
        "📅 Daily Automated Scheduling\n"
        "🔊 High-Quality Tamil Voice (XTTS-v2)\n\n"
        "Use /generate to start a video or /schedule to set daily time."
    )
    await update.message.reply_text(welcome_text)


async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger manual generation."""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return
    try:
        await update.message.reply_text(
            "🚀 Starting generation pipeline...\n"
            "⚠️ Note: Please wait for this to finish before starting another one to avoid AI rate limits (1 video every 2-3 minutes recommended)."
        )
        
        from core.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        job_id = await orchestrator.create_job()
        
        # Run in background to avoid bot timeout
        context.application.create_task(
            _run_and_notify(job_id, update.effective_chat.id, context)
        )
    except Exception as e:
        logger.error(f"Error in generate_command: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Failed to start generation: {str(e)}")


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set daily schedule. Usage: /schedule 10:00"""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return
    if not context.args:
        await update.message.reply_text("Usage: /schedule HH:MM (e.g., /schedule 09:30)")
        return
    
    time_str = context.args[0]
    if ":" not in time_str:
        await update.message.reply_text("Invalid time format. Use HH:MM")
        return

    try:
        Database = _get_db()
        _, _, Schedule, User, _, _ = _get_models()
        async with Database.get_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == update.effective_user.id))
            user = result.scalar_one_or_none()
            
            if not user:
                await update.message.reply_text("❌ User not found. Please run /start first.")
                return
            
            new_schedule = Schedule(user_id=user.id, publish_time=time_str, status="active")
            session.add(new_schedule)
            await session.commit()
        
        await update.message.reply_text(f"✅ Daily schedule set for {time_str} IST.")
    except Exception as e:
        logger.error(f"Error in schedule_command: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Failed to set schedule: {str(e)}")


async def view_schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all active schedules."""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return
    try:
        Database = _get_db()
        _, _, Schedule, _, _, _ = _get_models()
        async with Database.get_session() as session:
            result = await session.execute(select(Schedule).where(Schedule.status == "active"))
            schedules = result.scalars().all()
            
            if not schedules:
                await update.message.reply_text("No active schedules found. Use /schedule HH:MM to add one.")
                return
                
            text = "📅 Your Daily Schedules (IST):\n"
            for s in schedules:
                text += f"• {s.publish_time}\n"
            await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Error in view_schedule_command: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Failed to load schedules: {str(e)}")


async def clear_schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear all active schedules."""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return
    try:
        from sqlalchemy import delete
        Database = _get_db()
        _, _, Schedule, User, _, _ = _get_models()
        async with Database.get_session() as session:
            # Get user
            result = await session.execute(select(User).where(User.telegram_id == update.effective_user.id))
            user = result.scalar_one_or_none()
            
            if not user:
                await update.message.reply_text("❌ User not found.")
                return
                
            # Delete schedules
            await session.execute(delete(Schedule).where(Schedule.user_id == user.id))
            await session.commit()
            
            # Also tell the scheduler service to reload if it's available
            try:
                scheduler = context.application.bot_data.get("scheduler")
                if scheduler:
                    # Clear all jobs in APScheduler
                    scheduler.scheduler.remove_all_jobs()
            except Exception:
                pass
                
        await update.message.reply_text("🗑️ All active schedules have been revoked/cleared successfully.")
    except Exception as e:
        logger.error(f"Error in clear_schedule_command: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Failed to clear schedules: {str(e)}")


async def autopost_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle auto-approval mode."""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return
    if not context.args:
        await update.message.reply_text("Usage: /autopost [on/off]")
        return
    
    mode = context.args[0].lower()
    if mode not in ["on", "off"]:
        await update.message.reply_text("Invalid mode. Use 'on' or 'off'")
        return

    db_mode = "auto" if mode == "on" else "manual"
    
    try:
        from sqlalchemy import update as sql_update
        Database = _get_db()
        _, _, _, User, _, _ = _get_models()
        async with Database.get_session() as session:
            await session.execute(
                sql_update(User).where(User.telegram_id == update.effective_user.id).values(approval_mode=db_mode)
            )
            await session.commit()
        
        status_text = "🚀 AUTO-POST ENABLED. Videos will be posted to YouTube automatically at the scheduled time." if mode == "on" else "✋ MANUAL MODE ENABLED. You will need to approve videos in Telegram before they post."
        await update.message.reply_text(status_text)
    except Exception as e:
        logger.error(f"Error in autopost_command: {e}")
        await update.message.reply_text(f"❌ Failed to update mode: {str(e)}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check status of recent jobs."""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return
    try:
        Database = _get_db()
        Job, _, _, _, _, _ = _get_models()
        async with Database.get_session() as session:
            result = await session.execute(select(Job).order_by(Job.id.desc()).limit(5))
            jobs = result.scalars().all()
            
            if not jobs:
                await update.message.reply_text("📊 No recent jobs found. Use /generate to create one.")
                return
                
            status_text = "📊 Recent Job Status:\n\n"
            for j in jobs:
                date_str = j.planned_date.strftime('%Y-%m-%d %H:%M') if j.planned_date else "N/A"
                status_text += f"🔹 ID: {j.id} | {j.state.value} | {date_str}\n"
            
            await update.message.reply_text(status_text)
    except Exception as e:
        logger.error(f"Error in status_command: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Failed to check status: {str(e)}")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel operation."""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return
    await update.message.reply_text("⛔ Cancellation requested. New tasks will be blocked temporarily.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approval/regeneration buttons."""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data.startswith("approve_"):
            job_id = int(query.data.split("_")[1])
            await query.edit_message_caption("🚀 Approving and starting YouTube upload...")
            
            context.application.create_task(
                _run_upload_and_notify(job_id, query.message.chat_id, context)
            )
        elif query.data.startswith("regen_"):
            job_id = int(query.data.split("_")[1])
            await query.edit_message_caption("🔄 Regenerating video...")
            
            from core.orchestrator import Orchestrator
            orchestrator = Orchestrator()
            context.application.create_task(
                _run_and_notify(job_id, query.message.chat_id, context)
            )
    except Exception as e:
        logger.error(f"Error in button_callback: {e}")
        try:
            await query.edit_message_caption(f"❌ Error: {str(e)}")
        except:
            pass


async def _run_upload_and_notify(job_id, chat_id, context):
    """Run the upload and send confirmation."""
    try:
        from core.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        video_id = await orchestrator.publish_video(job_id)
        
        if video_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Video Uploaded Successfully!\n\nVideo ID: {video_id}\nURL: https://youtu.be/{video_id}\n\nStatus: Public (Live on YouTube)"
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ YouTube Upload Failed for Job {job_id}. Check logs for details."
            )
    except Exception as e:
        logger.error(f"Error in _run_upload_and_notify: {e}")
        logger.error(traceback.format_exc())
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Upload error: {str(e)}")


async def _run_and_notify(job_id, chat_id, context):
    """Run pipeline with REAL-TIME progress updates via callback."""
    status_msg = await context.bot.send_message(chat_id=chat_id, text="🔄 Initializing engine...")
    
    # Track last message to avoid editing with the same text
    last_text = [""]
    
    async def progress_callback(text):
        """Update the Telegram status message in real-time."""
        if text != last_text[0]:
            last_text[0] = text
            try:
                await status_msg.edit_text(text)
            except Exception as e:
                logger.warning(f"Could not update progress message: {e}")
    
    try:
        from core.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        
        success = await orchestrator.run_pipeline(job_id, progress_callback=progress_callback)
        
        if success:
            await status_msg.edit_text("📤 Sending video to Telegram...")

            from sqlalchemy import select
            from core.models import ScriptAsset, VideoAsset
            Database = _get_db()

            async with Database.get_session() as session:
                # Always fetch LATEST to handle regenerated jobs with multiple rows
                res_v = await session.execute(
                    select(VideoAsset).where(VideoAsset.job_id == job_id)
                    .order_by(VideoAsset.id.desc()).limit(1)
                )
                video = res_v.scalar_one_or_none()

                res_s = await session.execute(
                    select(ScriptAsset).where(ScriptAsset.job_id == job_id)
                    .order_by(ScriptAsset.id.desc()).limit(1)
                )
                script = res_s.scalar_one_or_none()

            if not video:
                await status_msg.edit_text("❌ Error: No video asset found in database")
                return

            video_path = video.draft_path
            if not os.path.exists(video_path):
                await status_msg.edit_text(f"❌ Error: Video file not found at {video_path}")
                return

            file_size = os.path.getsize(video_path)
            if file_size < 1024:
                await status_msg.edit_text(f"❌ Error: Video file too small ({file_size} bytes)")
                return

            score = script.similarity_score if script and script.similarity_score is not None else 0.0
            originality = 1.0 - score
            topic = script.topic if script else "Unknown"
            caption = (
                f"✅ Video Draft Ready!\n\n"
                f"📌 Topic: {topic}\n"
                f"📊 Originality Score: {originality:.2f}\n"
                f"📦 File Size: {file_size // 1024}KB\n\n"
                f"What would you like to do?"
            )

            keyboard = [
                [InlineKeyboardButton("🚀 Approve & Post to YouTube", callback_data=f"approve_{job_id}")],
                [InlineKeyboardButton("🔄 Regenerate", callback_data=f"regen_{job_id}")]
            ]

            import asyncio
            from telegram.error import RetryAfter, BadRequest

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with open(video_path, 'rb') as v:
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=v,
                            caption=caption,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            write_timeout=1200,
                            read_timeout=1200,
                            connect_timeout=1200
                        )
                    break
                except (RetryAfter, BadRequest) as e:
                    err_msg = str(e)
                    if "Too many requests" in err_msg or isinstance(e, RetryAfter):
                        retry_delay = getattr(e, 'retry_after', 10)
                        if attempt == max_retries - 1:
                            raise
                        logger.warning(f"Telegram rate limit hit. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(retry_delay + 1)
                    else:
                        raise
            await status_msg.delete()
        else:
            await status_msg.edit_text(f"❌ Job {job_id} failed. Use /status to check details.")

    except Exception as e:
        logger.error(f"Error in _run_and_notify: {e}")
        logger.error(traceback.format_exc())
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Pipeline error: {str(e)}")
        except Exception:
            pass
