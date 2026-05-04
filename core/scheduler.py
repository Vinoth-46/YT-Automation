import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from core.database import Database
from core.models import Schedule, User

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

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
        """The actual task that runs when scheduled."""
        from core.orchestrator import Orchestrator
        logger.info(f"Running scheduled task for schedule {schedule_id}")
        orchestrator = Orchestrator()
        job_id = await orchestrator.create_job(schedule_id=schedule_id)
        await orchestrator.run_pipeline(job_id)

    def stop(self):
        self.scheduler.shutdown()
        logger.info("Scheduler service stopped")
