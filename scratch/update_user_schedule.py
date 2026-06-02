import asyncio
import os
import sys
import logging
from sqlalchemy import select, delete, update

# Ensure absolute imports work from the repository root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import init_db, Database
from core.models import Schedule, User, Job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_user_schedule")

async def main():
    await init_db()
    
    async with Database.get_session() as session:
        # First query all active schedules
        result = await session.execute(select(Schedule))
        schedules = result.scalars().all()
        logger.info(f"Currently found {len(schedules)} schedules in the database.")
        
        # Get first user in DB if any
        res_user = await session.execute(select(User).limit(1))
        user = res_user.scalar_one_or_none()
        
        if not user:
            logger.error("No user found in the database. Run /start in Telegram first to register!")
            return
            
        logger.info(f"Selected user: ID {user.id}, Telegram ID {user.telegram_id}")
        
        if len(schedules) > 0:
            # Update the first schedule to 12:00
            first_schedule = schedules[0]
            logger.info(f"Updating first schedule (ID: {first_schedule.id}) to 12:00")
            first_schedule.publish_time = "12:00"
            first_schedule.status = "active"
            
            # For other schedules, decouple them from jobs first, then delete them
            other_schedule_ids = [s.id for s in schedules[1:]]
            if other_schedule_ids:
                logger.info(f"Decoupling jobs for other schedules: {other_schedule_ids}")
                # Set schedule_id = NULL for jobs referencing other schedules
                await session.execute(
                    update(Job).where(Job.schedule_id.in_(other_schedule_ids)).values(schedule_id=None)
                )
                await session.commit()
                
                logger.info(f"Deleting other schedules: {other_schedule_ids}")
                await session.execute(
                    delete(Schedule).where(Schedule.id.in_(other_schedule_ids))
                )
                await session.commit()
        else:
            # Create a brand new one
            logger.info("No schedules existed. Creating a new one for 12:00...")
            new_schedule = Schedule(user_id=user.id, publish_time="12:00", status="active", recurrence="daily")
            session.add(new_schedule)
            await session.commit()
            
        logger.info("Schedule successfully updated to exactly one daily posting at 12:00 IST.")

if __name__ == "__main__":
    asyncio.run(main())
