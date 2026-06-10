import os
import asyncio
import logging
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Telegram Bot API hard limit for send_video
TELEGRAM_MAX_BYTES = 49 * 1024 * 1024  # 49 MB (safe margin below 50 MB)


async def _compress_for_telegram(input_path: str) -> str:
    """Re-encode video to CRF 32 (~half the bitrate) so it fits under Telegram's 50 MB limit.
    Returns the path to the (possibly compressed) file.
    If the input is already small enough it is returned as-is.
    """
    size = os.path.getsize(input_path)
    if size <= TELEGRAM_MAX_BYTES:
        return input_path  # already fine

    compressed_path = input_path.replace(".mp4", "_tg.mp4")
    logger.info(
        f"Video is {size // (1024*1024)} MB — too large for Telegram. "
        f"Re-encoding to CRF 32 → {compressed_path}"
    )

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", "scale=720:1280",          # downscale 1080p→1280 short-side
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "32",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        compressed_path
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

    if proc.returncode != 0 or not os.path.exists(compressed_path):
        logger.error(f"Compression failed: {stderr.decode(errors='replace')[-300:]}")
        return input_path  # return original; send_video will raise and we handle below

    compressed_size = os.path.getsize(compressed_path)
    logger.info(f"Compressed: {size // (1024*1024)} MB → {compressed_size // (1024*1024)} MB")
    return compressed_path


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
        "Use /generate to start a video automatically, or /generate <your topic> to generate a custom video on a specific topic. Use /schedule to set daily time."
    )
    await update.message.reply_text(welcome_text)


async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger manual generation."""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return
    try:
        custom_topic = " ".join(context.args) if context.args else None
        
        start_msg = "🚀 Starting custom video generation pipeline...\n" if custom_topic else "🚀 Starting automatic video generation pipeline...\n"
        if custom_topic:
            start_msg += f"📌 Topic: {custom_topic}\n"
        start_msg += "⚠️ Note: Please wait for this to finish before starting another one to avoid AI rate limits (1 video every 2-3 minutes recommended)."
        
        await update.message.reply_text(start_msg)
        
        from core.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        job_id = await orchestrator.create_job(custom_topic=custom_topic)
        
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
    """Check status of recent jobs with rich detail."""
    if not _is_authorized(update):
        await _reject_unauthorized(update)
        return
    try:
        from core.models import ScriptAsset, VideoAsset, JobState
        Database = _get_db()
        Job, _, _, _, _, _ = _get_models()

        async with Database.get_session() as session:
            result = await session.execute(select(Job).order_by(Job.id.desc()).limit(5))
            jobs = result.scalars().all()

            if not jobs:
                await update.message.reply_text("📊 No recent jobs found. Use /generate to create one.")
                return

        # State → emoji mapping
        STATE_EMOJI = {
            "scheduled":          "🕐",
            "generating_script":  "📝",
            "generating_audio":   "🔊",
            "generating_visuals": "🎨",
            "rendering_draft":    "🎬",
            "awaiting_approval":  "⏳",
            "uploading":          "📤",
            "uploaded":           "✅",
            "failed":             "❌",
            "paused":             "⏸️",
        }

        # Stage → friendly name
        STAGE_NAME = {
            "scheduled":          "Scheduling",
            "generating_script":  "Script Generation",
            "generating_audio":   "Audio (TTS)",
            "generating_visuals": "Visual Fetch (Pexels)",
            "rendering_draft":    "FFmpeg Rendering",
            "awaiting_approval":  "Approval",
            "uploading":          "YouTube Upload",
            "upload":             "YouTube Upload",
            "unknown":            "Unknown Stage",
        }

        lines = ["📊 *Recent Jobs (last 5)*\n"]

        async with Database.get_session() as session:
            for j in jobs:
                state_val  = j.state.value if j.state else "unknown"
                emoji      = STATE_EMOJI.get(state_val, "🔹")
                date_str   = j.planned_date.strftime('%d %b %H:%M') if j.planned_date else "N/A"
                topic_str  = ""
                size_str   = ""
                yt_str     = ""

                # Fetch associated assets for extra detail
                try:
                    res_s = await session.execute(
                        select(ScriptAsset).where(ScriptAsset.job_id == j.id)
                        .order_by(ScriptAsset.id.desc()).limit(1)
                    )
                    script = res_s.scalar_one_or_none()
                    if script and script.topic:
                        topic_str = f"\n   📌 Topic: {script.topic[:60]}"

                    res_v = await session.execute(
                        select(VideoAsset).where(VideoAsset.job_id == j.id)
                        .order_by(VideoAsset.id.desc()).limit(1)
                    )
                    video = res_v.scalar_one_or_none()
                    if video:
                        if video.draft_path and os.path.exists(video.draft_path):
                            mb = os.path.getsize(video.draft_path) / (1024 * 1024)
                            size_str = f"\n   📦 Size: {mb:.1f} MB"
                        if video.final_path:
                            yt_str = f"\n   🔗 {video.final_path}"
                except Exception:
                    pass

                block = f"{emoji} *Job #{j.id}* — {state_val.upper()} ({date_str})"
                block += topic_str
                block += size_str
                block += yt_str

                # Rich failure explanation
                if state_val == "failed":
                    stage_name = STAGE_NAME.get(j.failed_stage or "", j.failed_stage or "Unknown")
                    err_msg    = j.error_message or "No error details saved."
                    block += f"\n   ⚠️ *Failed at:* {stage_name}"
                    block += f"\n   💬 *Reason:* {err_msg}"

                lines.append(block)

        msg = "\n\n".join(lines)
        await update.message.reply_text(msg, parse_mode="Markdown")

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
            # Clear buttons and set status caption to prevent duplicate clicks
            await query.edit_message_caption(
                caption="🚀 Approving and starting YouTube upload... Please wait.",
                reply_markup=None
            )
            
            context.application.create_task(
                _run_upload_and_notify(job_id, query.message.chat_id, context, query)
            )
        elif query.data.startswith("regen_"):
            job_id = int(query.data.split("_")[1])
            # Clear buttons and set status caption
            await query.edit_message_caption(
                caption="🔄 Video regeneration in progress... A new draft will be sent once rendered.",
                reply_markup=None
            )
            
            context.application.create_task(
                _run_and_notify(job_id, query.message.chat_id, context)
            )
    except Exception as e:
        logger.error(f"Error in button_callback: {e}")
        try:
            await query.edit_message_caption(f"❌ Callback Error: {str(e)}")
        except:
            pass


async def _run_upload_and_notify(job_id, chat_id, context, query=None):
    """Run the upload and send confirmation, updating Telegram message UI in-place."""
    try:
        from core.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        video_id = await orchestrator.publish_video(job_id)
        
        # Retrieve Script/Video metadata for updating the in-place caption
        from sqlalchemy import select
        from core.models import ScriptAsset, VideoAsset
        Database = _get_db()
        
        topic = "Unknown"
        originality = 0.0
        file_size_kb = 0
        
        try:
            async with Database.get_session() as session:
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
                
                if script:
                    topic = script.topic or "Unknown"
                    score = script.similarity_score if script.similarity_score is not None else 0.0
                    originality = 1.0 - score
                
                if video and video.draft_path and os.path.exists(video.draft_path):
                    file_size_kb = os.path.getsize(video.draft_path) // 1024
        except Exception as dbe:
            logger.warning(f"Failed to fetch metadata for caption update: {dbe}")
        
        if video_id:
            new_caption = (
                f"✅ Video Approved & Published!\n\n"
                f"📌 Topic: {topic}\n"
                f"📊 Originality Score: {originality:.2f}\n"
                f"📦 File Size: {file_size_kb}KB\n\n"
                f"🔗 YouTube Link: https://youtu.be/{video_id}\n\n"
                f"Video has been successfully posted to YouTube!"
            )
            keyboard = [
                [InlineKeyboardButton("🔄 Regenerate / Post Again", callback_data=f"regen_{job_id}")]
            ]
            
            if query:
                try:
                    await query.edit_message_caption(
                        caption=new_caption,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as qe:
                    logger.warning(f"Could not edit original message caption: {qe}")
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Video Uploaded Successfully!\n\nURL: https://youtu.be/{video_id}\nStatus: Public (Live on YouTube)"
            )
        else:
            new_caption = (
                f"❌ YouTube Upload Failed\n\n"
                f"📌 Topic: {topic}\n"
                f"Please try again or check the server logs."
            )
            keyboard = [
                [InlineKeyboardButton("🚀 Approve & Post to YouTube", callback_data=f"approve_{job_id}")],
                [InlineKeyboardButton("🔄 Regenerate", callback_data=f"regen_{job_id}")]
            ]
            
            if query:
                try:
                    await query.edit_message_caption(
                        caption=new_caption,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as qe:
                    logger.warning(f"Could not edit original message caption: {qe}")
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ YouTube Upload Failed for Job {job_id}. Please review logs."
            )
    except Exception as e:
        logger.error(f"Error in _run_upload_and_notify: {e}")
        logger.error(traceback.format_exc())
        
        # Fallback keyboard restore on unhandled exception
        try:
            if query:
                keyboard = [
                    [InlineKeyboardButton("🚀 Approve & Post to YouTube", callback_data=f"approve_{job_id}")],
                    [InlineKeyboardButton("🔄 Regenerate", callback_data=f"regen_{job_id}")]
                ]
                await query.edit_message_caption(
                    caption=f"❌ Upload Error: {str(e)}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception:
            pass
            
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
            from core.models import ScriptAsset, VideoAsset, Job
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

                res_j = await session.execute(
                    select(Job).where(Job.id == job_id)
                )
                job = res_j.scalar_one_or_none()

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
            
            from core.models import JobState
            is_uploaded = job.state == JobState.UPLOADED if job and job.state else False

            if is_uploaded:
                youtube_url = video.final_path or "https://youtu.be/Unknown"
                caption = (
                    f"🚀 Video Published Automatically (Auto-Post)!\n\n"
                    f"📌 Topic: {topic}\n"
                    f"📊 Originality Score: {originality:.2f}\n"
                    f"📦 File Size: {file_size // 1024}KB\n\n"
                    f"🔗 YouTube Link: {youtube_url}\n\n"
                    f"Video has been successfully posted to YouTube!"
                )
                keyboard = [
                    [InlineKeyboardButton("🔄 Regenerate / Post Again", callback_data=f"regen_{job_id}")]
                ]
            else:
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

            from telegram.error import RetryAfter, BadRequest

            # ── Compress if video exceeds Telegram's 50 MB limit ────────────
            try:
                send_path = await _compress_for_telegram(video_path)
            except Exception as ce:
                logger.warning(f"Compression step failed ({ce}), will try original file.")
                send_path = video_path

            send_size_mb = os.path.getsize(send_path) // (1024 * 1024)
            logger.info(f"Sending video to Telegram ({send_size_mb} MB): {send_path}")

            max_retries = 3
            sent_ok = False
            for attempt in range(max_retries):
                try:
                    with open(send_path, 'rb') as v:
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=v,
                            caption=caption,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            write_timeout=1200,
                            read_timeout=1200,
                            connect_timeout=1200
                        )
                    sent_ok = True
                    break
                except RetryAfter as e:
                    retry_delay = getattr(e, 'retry_after', 10)
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(f"Telegram rate limit hit. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(retry_delay + 1)
                except BadRequest as e:
                    if "request entity too large" in str(e).lower():
                        # Last resort: send as a downloadable document instead
                        logger.warning("Video still too large for send_video. Sending as document...")
                        try:
                            with open(send_path, 'rb') as v:
                                await context.bot.send_document(
                                    chat_id=chat_id,
                                    document=v,
                                    caption=caption + "\n\n⚠️ Sent as file (video too large for preview).",
                                    reply_markup=InlineKeyboardMarkup(keyboard),
                                    write_timeout=1200,
                                    read_timeout=1200,
                                    connect_timeout=1200
                                )
                        except Exception as de:
                            logger.error(f"Document fallback also failed: {de}")
                            raise
                        sent_ok = True
                        break
                    else:
                        raise

            # Clean up compressed temp file if we created one
            if send_path != video_path and os.path.exists(send_path):
                try:
                    os.remove(send_path)
                except Exception:
                    pass

            # Send a separate tap-to-copy metadata message for mobile convenience
            title = script.title if script else "Unknown Title"
            desc = script.description if script else "No Description"
            
            import re
            
            eng_desc = desc
            hindi_title = ""
            hindi_desc = ""
            spanish_title = ""
            spanish_desc = ""

            if "--- HINDI TRANSLATION ---" in desc:
                parts = desc.split("--- HINDI TRANSLATION ---")
                eng_desc = parts[0].strip()
                rest = parts[1]
                
                h_part = rest
                s_part = ""
                if "--- SPANISH TRANSLATION ---" in rest:
                    h_part, s_part = rest.split("--- SPANISH TRANSLATION ---")
                
                h_part = h_part.strip()
                h_title_match = re.search(r'TITLE:\s*(.*?)(?=\s*DESC:|$)', h_part, re.DOTALL)
                h_desc_match = re.search(r'DESC:\s*(.*)', h_part, re.DOTALL)
                if h_title_match:
                    hindi_title = h_title_match.group(1).strip()
                if h_desc_match:
                    hindi_desc = h_desc_match.group(1).strip()
                    
                if s_part:
                    s_part = s_part.strip()
                    s_title_match = re.search(r'TITLE:\s*(.*?)(?=\s*DESC:|$)', s_part, re.DOTALL)
                    s_desc_match = re.search(r'DESC:\s*(.*)', s_part, re.DOTALL)
                    if s_title_match:
                        spanish_title = s_title_match.group(1).strip()
                    if s_desc_match:
                        spanish_desc = s_desc_match.group(1).strip()
            
            def _escape_md(text):
                """Escape special characters for Telegram Markdown parse mode."""
                if not text:
                    return ""
                # For standard Markdown mode, escape problematic chars inside code blocks
                # Replace backticks which break code blocks
                return text.replace("`", "'").replace("*", "").replace("_", " ").replace("[", "(").replace("]", ")")
            
            safe_title = _escape_md(title)
            safe_eng_desc = _escape_md(eng_desc)
            
            safe_hindi_title = _escape_md(hindi_title)
            safe_hindi_desc = _escape_md(hindi_desc)
            
            safe_spanish_title = _escape_md(spanish_title)
            safe_spanish_desc = _escape_md(spanish_desc)
            
            metadata_message = (
                f"📋 *YOUTUBE METADATA* (Tap text to copy)\n\n"
                f"🇬🇧 *ENGLISH*\n"
                f"🔹 *Title:*\n`{safe_title}`\n\n"
                f"🔹 *Description:*\n`{safe_eng_desc}`\n\n"
            )
            
            if hindi_title:
                metadata_message += (
                    f"🇮🇳 *HINDI (हिन्दी)*\n"
                    f"🔹 *Title:*\n`{safe_hindi_title}`\n\n"
                    f"🔹 *Description:*\n`{safe_hindi_desc}`\n\n"
                )
                
            if spanish_title:
                metadata_message += (
                    f"🇪🇸 *SPANISH (ESPAÑOL)*\n"
                    f"🔹 *Title:*\n`{safe_spanish_title}`\n\n"
                    f"🔹 *Description:*\n`{safe_spanish_desc}`\n\n"
                )
            
            # Trim trailing newlines
            metadata_message = metadata_message.strip()
            
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=metadata_message,
                    parse_mode="Markdown"
                )
            except Exception as me:
                # Fallback: send without formatting if Markdown still fails
                logger.warning(f"Markdown metadata message failed: {me}. Sending plain text.")
                try:
                    plain_message = (
                        f"📋 YouTube Metadata (Tap to copy):\n\n"
                        f"🇬🇧 ENGLISH:\n"
                        f"🔹 Title:\n{title}\n\n"
                        f"🔹 Description:\n{eng_desc}\n\n"
                    )
                    if hindi_title:
                        plain_message += (
                            f"🇮🇳 HINDI:\n"
                            f"🔹 Title:\n{hindi_title}\n\n"
                            f"🔹 Description:\n{hindi_desc}\n\n"
                        )
                    if spanish_title:
                        plain_message += (
                            f"🇪🇸 SPANISH:\n"
                            f"🔹 Title:\n{spanish_title}\n\n"
                            f"🔹 Description:\n{spanish_desc}\n\n"
                        )
                    plain_message = plain_message.strip()
                    await context.bot.send_message(chat_id=chat_id, text=plain_message)
                except Exception as pe:
                    logger.error(f"Could not send metadata message at all: {pe}")

            await status_msg.delete()
        else:
            await status_msg.edit_text(f"❌ Job {job_id} failed. Use /status to check details.")

    except Exception as e:
        logger.error(f"Error in _run_and_notify: {e}")
        logger.error(traceback.format_exc())
        try:
            from core.orchestrator import Orchestrator
            orchestrator = Orchestrator()
            await orchestrator._fail_job(job_id, "telegram_delivery", e)
        except Exception as fe:
            logger.error(f"Failed to mark job as failed: {fe}")
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Pipeline error: {str(e)}")
        except Exception:
            pass
