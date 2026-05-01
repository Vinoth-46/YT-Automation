import os
import logging
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

logger = logging.getLogger(__name__)


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
                logger.info(f"Creating new user {user.id} in database...")
                db_user = User(telegram_id=user.id, timezone="UTC")
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
        
        await update.message.reply_text(f"✅ Daily schedule set for {time_str} UTC.")
    except Exception as e:
        logger.error(f"Error in schedule_command: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Failed to set schedule: {str(e)}")


async def view_schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all active schedules."""
    try:
        Database = _get_db()
        _, _, Schedule, _, _, _ = _get_models()
        async with Database.get_session() as session:
            result = await session.execute(select(Schedule).where(Schedule.status == "active"))
            schedules = result.scalars().all()
            
            if not schedules:
                await update.message.reply_text("No active schedules found. Use /schedule HH:MM to add one.")
                return
                
            text = "📅 Your Daily Schedules (UTC):\n"
            for s in schedules:
                text += f"• {s.publish_time}\n"
            await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Error in view_schedule_command: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(f"❌ Failed to load schedules: {str(e)}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check status of recent jobs."""
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
    await update.message.reply_text("⛔ Cancellation requested. New tasks will be blocked temporarily.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approval/regeneration buttons."""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data.startswith("approve_"):
            job_id = int(query.data.split("_")[1])
            await query.edit_message_text("🚀 Approving and starting YouTube upload...")
            
            context.application.create_task(
                _run_upload_and_notify(job_id, query.message.chat_id, context)
            )
        elif query.data.startswith("regen_"):
            job_id = int(query.data.split("_")[1])
            await query.edit_message_text("🔄 Regenerating video...")
            
            from core.orchestrator import Orchestrator
            orchestrator = Orchestrator()
            context.application.create_task(
                _run_and_notify(job_id, query.message.chat_id, context)
            )
    except Exception as e:
        logger.error(f"Error in button_callback: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")


async def _run_upload_and_notify(job_id, chat_id, context):
    """Run the upload and send confirmation."""
    try:
        from core.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        video_id = await orchestrator.publish_video(job_id)
        
        if video_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Video Uploaded Successfully!\n\nVideo ID: {video_id}\nURL: https://youtu.be/{video_id}\n\nStatus: Private (Check YouTube Studio to publish)"
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
    """Run pipeline with REAL-TIME progress updates."""
    status_msg = await context.bot.send_message(chat_id=chat_id, text="🔄 Initializing engine...")
    
    try:
        from core.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        
        # We'll update the progress message as we go
        await status_msg.edit_text("📝 Stage 1/3: Generating AI Script & Visual Keywords...")
        
        success = await orchestrator.run_pipeline(job_id)
        
        if success:
            await status_msg.edit_text("🎬 Stage 3/3: Video Assembled! Sending to you...")
            
            Database = _get_db()
            Job, _, _, _, _, _ = _get_models()
            async with Database.get_session() as session:
                from sqlalchemy.orm import selectinload
                result = await session.execute(
                    select(Job).options(
                        selectinload(Job.video),
                        selectinload(Job.script)
                    ).where(Job.id == job_id)
                )
                job = result.scalar_one()
                
                video_path = job.video.draft_path
                if not os.path.exists(video_path):
                    await status_msg.edit_text(f"❌ Error: Video file not found at {video_path}")
                    return

                score = job.script.similarity_score if job.script.similarity_score is not None else 0.0
                caption = (
                    f"✅ Video Draft Ready!\n\n"
                    f"📌 Topic: {job.script.topic}\n"
                    f"📊 Originality Score: {score:.2f}\n\n"
                    f"What would you like to do?"
                )
                
                keyboard = [
                    [InlineKeyboardButton("🚀 Approve & Post to YouTube", callback_data=f"approve_{job_id}")],
                    [InlineKeyboardButton("🔄 Regenerate", callback_data=f"regen_{job_id}")]
                ]
                
                with open(video_path, 'rb') as v:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=v,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        write_timeout=300
                    )
                await status_msg.delete()
        else:
            await status_msg.edit_text(f"❌ Job {job_id} failed. Check /status.")
            
    except Exception as e:
        logger.error(f"Error in _run_and_notify: {e}")
        logger.error(traceback.format_exc())
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Pipeline error: {str(e)}")
        except Exception:
            pass
