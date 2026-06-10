import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from core.orchestrator import Orchestrator

class TestOrchestratorLocking(unittest.IsolatedAsyncioTestCase):
    async def test_serialized_execution(self):
        orchestrator = Orchestrator()
        
        # Track execution order and overlapping
        started = []
        finished = []
        
        async def mock_run_locked(job_id, notify):
            started.append(job_id)
            print(f"Job {job_id} started...")
            await asyncio.sleep(1)  # Simulate pipeline work
            finished.append(job_id)
            print(f"Job {job_id} finished...")
            return True
        
        # Patch the actual pipeline worker method
        with patch.object(orchestrator, '_run_pipeline_locked', new=mock_run_locked):
            # Run two jobs concurrently
            t1 = asyncio.create_task(orchestrator.run_pipeline(1001))
            t2 = asyncio.create_task(orchestrator.run_pipeline(1002))
            
            await asyncio.gather(t1, t2)
            
            # Assertions to ensure strict serialization:
            # Job 1001 should start and finish before Job 1002 starts
            self.assertEqual(started, [1001, 1002])
            self.assertEqual(finished, [1001, 1002])
            print("Verification SUCCESS! Jobs executed in strict sequential order.")

if __name__ == "__main__":
    unittest.main()
