import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from core.database import Database
from core.models import Schedule, User
from core.config import settings

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self, bot=None):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        self.bot = bot  # Telegram bot reference for notifications

    def start(self):
        self.scheduler.start()
        logger.info("Scheduler service started")

    async def load_schedules(self):
        """Load active schedules from the database and add to APScheduler."""
        async with Database.get_session() as session:
            result = await session.execute(select(Schedule).where(Schedule.status == "active"))
            schedules = result.scalars().all()
            
            for sched in schedules:
                self.add_schedule_job(sched)

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

    async def _run_scheduled_task(self, schedule_id):
        """The actual task that runs when scheduled, with Telegram notifications."""
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
        
        # Build a progress callback for Telegram if bot is available
        async def notify_telegram(text):
            if self.bot and chat_ids:
                try:
                    for cid in chat_ids[:1]:  # Notify first chat only
                        await self.bot.send_message(chat_id=cid, text=f"⏰ Scheduled Job #{job_id}: {text}")
                except Exception as e:
                    logger.warning(f"Telegram notification failed: {e}")
        
        success = await orchestrator.run_pipeline(job_id, progress_callback=notify_telegram)
        
        if success and self.bot and chat_ids:
            try:
                for cid in chat_ids[:1]:
                    await self.bot.send_message(
                        chat_id=cid,
                        text=f"✅ Scheduled video (Job #{job_id}) is ready! Use /status to check."
                    )
            except Exception as e:
                logger.warning(f"Completion notification failed: {e}")

    def stop(self):
        self.scheduler.shutdown()
        logger.info("Scheduler service stopped")
