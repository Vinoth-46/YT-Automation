import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select
from core.database import Database
from core.models import Job, JobState, Schedule, User, ScriptAsset, VideoAsset
from core.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    # Ensure user exists in DB
    async with Database.get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            db_user = User(telegram_id=user.id, timezone="UTC")
            session.add(db_user)
            await session.commit()

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
    await update.message.reply_text("Starting generation pipeline... 🏗️")
    orchestrator = Orchestrator()
    job_id = await orchestrator.create_job()
    
    # Run in background to avoid bot timeout
    context.application.create_task(
        _run_and_notify(job_id, update.effective_chat.id, context)
    )

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set daily schedule. Usage: /schedule 10:00"""
    if not context.args:
        await update.message.reply_text("Usage: /schedule HH:MM (e.g., /schedule 09:30)")
        return
    
    time_str = context.args[0]
    # Simple validation
    if ":" not in time_str:
        await update.message.reply_text("Invalid time format. Use HH:MM")
        return

    async with Database.get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == update.effective_user.id))
        user = result.scalar_one_or_none()
        
        new_schedule = Schedule(user_id=user.id, publish_time=time_str, status="active")
        session.add(new_schedule)
        await session.commit()
    
    await update.message.reply_text(f"✅ Daily schedule set for {time_str} UTC.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check status of recent jobs."""
    async with Database.get_session() as session:
        result = await session.execute(select(Job).order_by(Job.id.desc()).limit(5))
        jobs = result.scalars().all()
        
        if not jobs:
            await update.message.reply_text("No recent jobs found.")
            return
            
        status_text = "Recent Job Status:\n"
        for j in jobs:
            status_text += f"ID: {j.id} | State: {j.state.value} | Date: {j.planned_date.strftime('%Y-%m-%d %H:%M')}\n"
        
        await update.message.reply_text(status_text)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approval/regeneration buttons."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("approve_"):
        job_id = int(query.data.split("_")[1])
        await query.edit_message_text("🚀 Approving and starting YouTube upload...")
        
        orchestrator = Orchestrator()
        # Run upload in background
        context.application.create_task(
            _run_upload_and_notify(job_id, query.message.chat_id, context)
        )

async def _run_upload_and_notify(job_id, chat_id, context):
    """Run the upload and send confirmation."""
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

async def _run_and_notify(job_id, chat_id, context):
    """Run pipeline and send the draft to Telegram."""
    orchestrator = Orchestrator()
    success = await orchestrator.run_pipeline(job_id)
    
    if success:
        # Inform user about progress
        await context.bot.send_message(chat_id=chat_id, text="🏗️ Video draft generated! Now uploading to Telegram...")
        
        async with Database.get_session() as session:
            # Fetch Job with script and video details eager loaded to prevent MissingGreenlet
            from sqlalchemy.orm import selectinload
            result = await session.execute(
                select(Job).options(
                    selectinload(Job.video),
                    selectinload(Job.script)
                ).where(Job.id == job_id)
            )
            job = result.scalar_one()
            
            video_path = job.video.draft_path
            
            # Crash protection: Ensure score is not None
            score = job.script.similarity_score if job.script.similarity_score is not None else 0.0
            caption = f"✅ Video Draft Ready!\n\nTopic: {job.script.topic}\nScore: {score:.2f}"

            
            keyboard = [
                [InlineKeyboardButton("👍 Approve", callback_data=f"approve_{job_id}")],
                [InlineKeyboardButton("🔄 Regenerate", callback_data=f"regen_{job_id}")]
            ]
            
            try:
                with open(video_path, 'rb') as v:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=v,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        write_timeout=120 # Give it more time for large files
                    )
            except Exception as e:
                logger.error(f"Failed to send video to Telegram: {e}")
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=f"❌ Video is ready but Telegram upload failed: {str(e)}\n\nYou can find it at: {video_path}"
                )
    else:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Job {job_id} failed. Check /status.")

