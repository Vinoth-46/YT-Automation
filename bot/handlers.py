from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.config import settings
from core.orchestrator import Orchestrator
from core.database import get_jobs_collection
from utils.youtube_uploader import YouTubeUploader
import logging
import os

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    welcome_text = (
        f"வணக்கம் {user.first_name}! 👋\n\n"
        "Welcome to the Civil Engineering AI Video Automation Bot.\n\n"
        "I can help you generate high-quality YouTube Shorts in Tamil.\n"
        "Use the buttons below to get started."
    )
    
    keyboard = [
        [InlineKeyboardButton("🚀 Generate Video Now", callback_data="generate_now")],
        [InlineKeyboardButton("📅 Schedule Daily Job", callback_data="schedule_job")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    # Placeholder for actual job status from DB
    await update.message.reply_text("Current System Status: Online 🟢\nNo active jobs.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "generate_now":
        await query.edit_message_text("Starting immediate generation... 🏗️\n(This will take a few minutes)")
        
        orchestrator = Orchestrator()
        job_id, video_path, script_data = await orchestrator.run_full_generation(update.effective_chat.id)
        
        if video_path and os.path.exists(video_path):
            # Send the video to the user for review
            caption = (
                f"✅ Video Draft Ready!\n\n"
                f"Topic: {script_data['metadata']['title']}\n\n"
                "What would you like to do?"
            )
            keyboard = [
                [InlineKeyboardButton("👍 Approve & Upload", callback_data=f"approve_{job_id}")],
                [InlineKeyboardButton("🔄 Regenerate", callback_data=f"regenerate_{job_id}")],
                [InlineKeyboardButton("❌ Discard", callback_data=f"discard_{job_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Use send_video for the draft
            with open(video_path, 'rb') as video:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=video,
                    caption=caption,
                    reply_markup=reply_markup
                )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Sorry, generation failed. Please try again or check logs."
            )
    elif query.data.startswith("approve_"):
        job_id = query.data.replace("approve_", "")
        await query.edit_message_text("🚀 Uploading to YouTube... Please wait.")
        
        # Fetch job details from DB
        jobs = get_jobs_collection()
        job = await jobs.find_one({"job_id": job_id})
        
        if job and "video_path" in job:
            uploader = YouTubeUploader()
            if not uploader:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ YouTube authentication failed. check credentials/ folder.")
                return

            video_id = await uploader.upload_video(
                video_path=job["video_path"],
                title=job["script"]["metadata"]["title"],
                description=job["script"]["metadata"]["description"],
                tags=job["script"]["metadata"].get("tags", [])
            )
            
            if video_id:
                await query.edit_message_text(f"✅ Successfully uploaded! \nVideo ID: {video_id}\n\nNote: Uploaded as PRIVATE (as per safety settings).")
            else:
                await query.edit_message_text("❌ Upload failed. Check logs for details.")
        else:
            await query.edit_message_text("❌ Error: Could not find video file for this job.")
    
    elif query.data == "schedule_job":
        await query.edit_message_text("Scheduling features coming soon! 📅")
    elif query.data == "settings":
        await query.edit_message_text("Settings menu placeholder. ⚙️")
