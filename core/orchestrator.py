import uuid
import logging
from engines.script_engine import ScriptEngine
from engines.audio_engine import AudioEngine
from engines.video_engine import VideoEngine
from core.database import get_jobs_collection

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self):
        self.script_engine = ScriptEngine()
        self.audio_engine = AudioEngine()
        self.video_engine = VideoEngine()

    async def run_full_generation(self, chat_id):
        """Orchestrate the full video generation pipeline."""
        job_id = str(uuid.uuid4())
        jobs = get_jobs_collection()
        
        # 1. Initialize Job
        await jobs.insert_one({
            "job_id": job_id,
            "chat_id": chat_id,
            "status": "generating_topic"
        })
        
        try:
            # 2. Topic Generation
            topic = await self.script_engine.generate_topic()
            await jobs.update_one({"job_id": job_id}, {"$set": {"status": "generating_script", "topic": topic}})
            
            # 3. Script Generation
            script_data = await self.script_engine.generate_script(topic)
            if not script_data:
                raise Exception("Script generation failed")
            await jobs.update_one({"job_id": job_id}, {"$set": {"status": "generating_audio", "script": script_data}})
            
            # 4. Audio Generation (Gemini latest voice)
            narration_path = await self.audio_engine.generate_narration(script_data, job_id)
            if not narration_path:
                raise Exception("Audio generation failed")
            await jobs.update_one({"job_id": job_id}, {"$set": {"status": "assembling_video", "narration_path": narration_path}})
            
            # 5. Video Assembly
            video_path = await self.video_engine.assemble_video(job_id, narration_path, script_data)
            if not video_path:
                raise Exception("Video assembly failed")
            
            # 6. Finalize
            await jobs.update_one({"job_id": job_id}, {
                "$set": {
                    "status": "awaiting_approval",
                    "video_path": video_path
                }
            })
            
            return job_id, video_path, script_data

        except Exception as e:
            logger.error(f"Generation job {job_id} failed: {e}")
            await jobs.update_one({"job_id": job_id}, {"$set": {"status": "failed", "error": str(e)}})
            return job_id, None, None
