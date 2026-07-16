import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, update
from core.database import Database
from core.models import Schedule, User
from core.config import settings

logger = logging.getLogger(__name__)

# ── Default fully-automatic schedule at 03:30 IST ────────────────────────────
# 03:30 AM IST = ~10:00 PM UTC (previous day)
# This is the LOWEST global traffic window for Hugging Face Spaces:
#   - US is sleeping (10 PM ET)
#   - Europe hasn't woken up (midnight CET)
#   - China/Asia is finishing work
# AI video generation on Wan 2.1 HF Space is fastest at this hour.
AUTO_SCHEDULE_TIME = "03:30"
AUTO_SCHEDULE_TAG  = "auto_morning_publish"   # sentinel job-id in APScheduler
# ─────────────────────────────────────────────────────────────────────────────

class SchedulerService:
    def __init__(self, bot=None):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        self.bot = bot  # Telegram bot reference for notifications

    def start(self):
        self.scheduler.start()
        logger.info("Scheduler service started")

    async def reload_schedules(self):
        """Clear all jobs and reload schedules from the database."""
        self.scheduler.remove_all_jobs()
        await self.load_schedules()

    async def load_schedules(self):
        """Load active schedules from the database and add to APScheduler.
        Also ensures the hardcoded auto-publish job always exists.
        """
        async with Database.get_session() as session:
            # Automatically migrate active old schedules to match the new low-traffic preference
            for old_time in ["12:00", "08:00"]:
                await session.execute(
                    update(Schedule)
                    .where(Schedule.publish_time == old_time)
                    .where(Schedule.status == "active")
                    .values(publish_time=AUTO_SCHEDULE_TIME)
                )
            await session.commit()

            result = await session.execute(select(Schedule).where(Schedule.status == "active"))
            schedules = result.scalars().all()
            
            for sched in schedules:
                self.add_schedule_job(sched)

        # Always guarantee the auto-publish job is registered unless a DB schedule exists at the same time
        has_morning_db_schedule = any(s.publish_time == AUTO_SCHEDULE_TIME for s in schedules)
        if not has_morning_db_schedule:
            self._ensure_auto_morning_job()
        else:
            if self.scheduler.get_job(AUTO_SCHEDULE_TAG):
                self.scheduler.remove_job(AUTO_SCHEDULE_TAG)
            logger.info(f"Skipped registering hardcoded morning auto-publish because a database schedule already exists for {AUTO_SCHEDULE_TIME}")


    def _ensure_auto_morning_job(self):
        """Register (or re-register) the daily fully-automatic publish job."""
        hour, minute = AUTO_SCHEDULE_TIME.split(":")
        if self.scheduler.get_job(AUTO_SCHEDULE_TAG):
            self.scheduler.remove_job(AUTO_SCHEDULE_TAG)
        self.scheduler.add_job(
            self._run_auto_publish,
            CronTrigger(hour=hour, minute=minute),
            id=AUTO_SCHEDULE_TAG,
            name=f"🌙 Daily Auto-Publish at {AUTO_SCHEDULE_TIME} IST",
        )
        logger.info(f"✅ Auto-publish job guaranteed at {AUTO_SCHEDULE_TIME} IST (ID: {AUTO_SCHEDULE_TAG})")

    def add_schedule_job(self, schedule: Schedule):
        """Add a single schedule to the running scheduler."""
        hour, minute = schedule.publish_time.split(":")
        job_id = f"schedule_{schedule.id}"
        
        # Remove existing if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            
        self.scheduler.add_job(
            self._run_scheduled_task,
            CronTrigger(hour=hour, minute=minute),
            id=job_id,
            args=[schedule.id]
        )
        logger.info(f"Added scheduled task for schedule {schedule.id} at {schedule.publish_time}")

    async def _notify(self, text: str, chat_ids: list):
        """Send a Telegram message to each chat_id. Silently ignores errors."""
        if self.bot and chat_ids:
            for cid in chat_ids[:1]:   # notify first chat only
                try:
                    await self.bot.send_message(chat_id=cid, text=text)
                except Exception as e:
                    logger.warning(f"Telegram notification failed: {e}")

    async def _run_auto_publish(self):
        """Fully-automatic daily pipeline: Script → Audio → Video → YouTube.
        
        This job runs at 08:00 IST every day. It does NOT require /autopost on
        or any database approval_mode — it always publishes straight to YouTube.
        A Telegram message is sent at each major stage and a final confirmation
        with the YouTube link is sent when done.
        """
        from core.orchestrator import Orchestrator

        chat_ids = settings.ALLOWED_CHAT_IDS
        logger.info(f"🌙 {AUTO_SCHEDULE_TIME} auto-publish job triggered")

        await self._notify(
            f"🌙 {AUTO_SCHEDULE_TIME} AM Auto-Publish started!\n\n"
            "📝 Stage 1/4: Generating AI Script...",
            chat_ids
        )

        orchestrator = Orchestrator()
        job_id = await orchestrator.create_job()

        # ── Stage callbacks ───────────────────────────────────────────────────
        last_stage = [""]
        async def progress(text):
            if text != last_stage[0]:
                last_stage[0] = text
                await self._notify(f"⏳ Job #{job_id}: {text}", chat_ids)

        # ── Run full pipeline (script + audio + video) ────────────────────────
        success = await orchestrator.run_pipeline(job_id, progress_callback=progress)

        if not success:
            await self._notify(
                f"❌ Auto-publish failed at Job #{job_id}.\n"
                "Check Kaggle logs for details.",
                chat_ids
            )
            return

        # ── Auto-upload to YouTube ────────────────────────────────────────────
        await self._notify(
            f"✅ Video rendered! Job #{job_id}\n"
            "🚀 Uploading to YouTube now...",
            chat_ids
        )

        try:
            video_id = await orchestrator.publish_video(job_id)
        except Exception as pub_err:
            await self._notify(
                f"❌ YouTube upload failed for Job #{job_id}: {pub_err}",
                chat_ids
            )
            return

        if video_id:
            youtube_url = f"https://youtu.be/{video_id}"
            await self._notify(
                f"🎉 Video Published Successfully!\n\n"
                f"📌 Job: #{job_id}\n"
                f"🔗 {youtube_url}\n\n"
                f"The video is now LIVE on YouTube! ✅",
                chat_ids
            )
            logger.info(f"Auto-publish complete: {youtube_url}")
        else:
            await self._notify(
                f"⚠️ Upload may have failed — no video ID returned for Job #{job_id}.",
                chat_ids
            )

    async def _run_scheduled_task(self, schedule_id):
        """Manual-schedule task (added via /schedule command) with Telegram notifications."""
        from core.orchestrator import Orchestrator
        logger.info(f"Running scheduled task for schedule {schedule_id}")
        
        # Resolve the user's Telegram ID for notifications
        chat_ids = []
        try:
            async with Database.get_session() as session:
                res = await session.execute(
                    select(Schedule).where(Schedule.id == schedule_id)
                )
                schedule = res.scalar_one_or_none()
                if schedule:
                    user_res = await session.execute(
                        select(User).where(User.id == schedule.user_id)
                    )
                    user = user_res.scalar_one_or_none()
                    if user and user.telegram_id:
                        chat_ids.append(user.telegram_id)
        except Exception as e:
            logger.warning(f"Could not resolve Telegram chat ID for schedule {schedule_id}: {e}")
        
        # Fallback to configured chat IDs if no user-specific ID
        if not chat_ids:
            chat_ids = settings.ALLOWED_CHAT_IDS
        
        orchestrator = Orchestrator()
        job_id = await orchestrator.create_job(schedule_id=schedule_id)
        
        async def notify_telegram(text):
            await self._notify(f"⏰ Scheduled Job #{job_id}: {text}", chat_ids)
        
        success = await orchestrator.run_pipeline(job_id, progress_callback=notify_telegram)
        
        if success and self.bot and chat_ids:
            await self._notify(
                f"✅ Scheduled video (Job #{job_id}) is ready! Use /status to check.",
                chat_ids
            )

    def stop(self):
        self.scheduler.shutdown()
        logger.info("Scheduler service stopped")
