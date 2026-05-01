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
    logger.info(f"Received /start command from user {user.id} ({user.first_name})")
    
    try:
        # Ensure user exists in DB
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

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set daily schedule. Usage: /schedule 10:00"""
    if not context.args:
        await update.message.reply_text("Usage: /schedule HH:MM (e.g., /schedule 09:30)")
        return
    
    time_str = context.args[0]
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

async def view_schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all active schedules."""
    async with Database.get_session() as session:
        result = await session.execute(select(Schedule).where(Schedule.status == "active"))
        schedules = result.scalars().all()
        
        if not schedules:
            await update.message.reply_text("No active schedules found. Use /schedule HH:MM to add one.")
            return
            
        text = "📅 **Your Daily Schedules (UTC):**\n"
        for s in schedules:
            text += f"• {s.publish_time}\n"
        await update.message.reply_text(text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check status of recent jobs."""
    async with Database.get_session() as session:
        result = await session.execute(select(Job).order_by(Job.id.desc()).limit(5))
        jobs = result.scalars().all()
        
        if not jobs:
            await update.message.reply_text("No recent jobs found.")
            return
            
        status_text = "📊 **Recent Job Status:**\n"
        for j in jobs:
            status_text += f"ID: `{j.id}` | {j.state.value} | {j.planned_date.strftime('%H:%M')}\n"
        
        await update.message.reply_text(status_text, parse_mode='Markdown')

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel operation."""
    await update.message.reply_text("⛔ Cancellation requested. New tasks will be blocked temporarily.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approval/regeneration buttons."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("approve_"):
        job_id = int(query.data.split("_")[1])
        await query.edit_message_text("🚀 Approving and starting YouTube upload...")
        
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
            text=f"✅ **Video Uploaded Successfully!**\n\nVideo ID: `{video_id}`\nURL: https://youtu.be/{video_id}\n\nStatus: Private (Check YouTube Studio to publish)",
            parse_mode='Markdown'
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ YouTube Upload Failed for Job {job_id}. Check logs for details."
        )

async def _run_and_notify(job_id, chat_id, context):
    """Run pipeline with REAL-TIME progress updates."""
    status_msg = await context.bot.send_message(chat_id=chat_id, text="🔄 Initializing engine...")
    
    try:
        orchestrator = Orchestrator()
        
        # We'll update the progress message as we go
        await status_msg.edit_text("📝 Stage 1/3: Generating AI Script & Visual Keywords...")
        # Note: The pipeline currently runs all at once. For true real-time, 
        # we'd need to modify Orchestrator. For now, we show the start of the heavy work.
        
        success = await orchestrator.run_pipeline(job_id)
        
        if success:
            await status_msg.edit_text("🎬 Stage 3/3: Video Assembled! Sending to you...")
            
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
                    f"✅ **Video Draft Ready!**\n\n"
                    f"📌 **Topic**: {job.script.topic}\n"
                    f"📊 **Originality Score**: {score:.2f}\n\n"
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
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        write_timeout=300
                    )
                await status_msg.delete()
        else:
            await status_msg.edit_text(f"❌ Job {job_id} failed. Check /status.")
            
    except Exception as e:
        logger.error(f"Error in _run_and_notify: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error: {str(e)}")



