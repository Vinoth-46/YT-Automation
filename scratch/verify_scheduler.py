import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from core.scheduler import SchedulerService
from core.models import Schedule

class TestSchedulerDoublePublish(unittest.IsolatedAsyncioTestCase):
    @patch('core.scheduler.Database')
    async def test_scheduler_noon_job_registration(self, mock_db):
        # Create a mock database session
        mock_session = AsyncMock()
        mock_db.get_session.return_value.__aenter__.return_value = mock_session
        
        # Test Case 1: No active database schedules at 12:00
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        
        scheduler_service = SchedulerService()
        
        # Mock ensure_auto_noon_job and add_schedule_job to track calls
        scheduler_service._ensure_auto_noon_job = MagicMock()
        scheduler_service.add_schedule_job = MagicMock()
        scheduler_service.scheduler = MagicMock()
        
        await scheduler_service.load_schedules()
        
        # Asserts: Should register the hardcoded noon job
        scheduler_service._ensure_auto_noon_job.assert_called_once()
        print("Test Case 1 passed: Noon job registered when no DB schedule exists.")

        # Test Case 2: Active database schedule exists at 12:00
        mock_sched = Schedule(publish_time="12:00", status="active")
        mock_result.scalars.return_value.all.return_value = [mock_sched]
        
        scheduler_service = SchedulerService()
        scheduler_service._ensure_auto_noon_job = MagicMock()
        scheduler_service.add_schedule_job = MagicMock()
        scheduler_service.scheduler = MagicMock()
        
        await scheduler_service.load_schedules()
        
        # Asserts: Should NOT register the hardcoded noon job
        scheduler_service._ensure_auto_noon_job.assert_not_called()
        scheduler_service.scheduler.get_job.assert_called_with("auto_noon_publish")
        print("Test Case 2 passed: Noon job skipped when active DB schedule at 12:00 exists.")

if __name__ == "__main__":
    unittest.main()
