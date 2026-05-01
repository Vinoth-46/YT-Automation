import logging
from datetime import datetime
from sqlalchemy import select, update
from core.database import Database
from core.models import Job, JobState, ScriptAsset, AudioAsset, VideoAsset
from engines.script_engine import ScriptEngine
from engines.audio_engine import AudioEngine
from engines.video_engine import VideoEngine

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self):
        self.script_engine = ScriptEngine()
        self.audio_engine = AudioEngine()
        self.video_engine = VideoEngine()

    async def create_job(self, schedule_id=None, planned_date=None):
        """Create a new job record in the database."""
        async with Database.get_session() as session:
            job = Job(
                schedule_id=schedule_id,
                planned_date=planned_date or datetime.now(),
                state=JobState.SCHEDULED
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job.id

    async def run_pipeline(self, job_id):
        """Execute the full 10-state lifecycle for a job."""
        try:
            # 1. Start Content Generation (Topic + Script)
            await self._update_job_state(job_id, JobState.GENERATING_SCRIPT)
            
            # Fetch past topics for exclusion
            async with Database.get_session() as session:
                from core.models import ScriptAsset
                res = await session.execute(select(ScriptAsset.topic).limit(20))
                existing_topics = res.scalars().all()

            # Mega-Prompt Call
            full_data = await self.script_engine.generate_full_content(existing_topics)
            if not full_data:
                raise Exception("Content generation (Mega-Prompt) failed")
            
            topic_data = full_data['topic']
            script_data = full_data['script']
            
            async with Database.get_session() as session:
                script_asset = ScriptAsset(
                    job_id=job_id,
                    topic=topic_data.get("title_en"),
                    script_text=script_data.get("narration"),
                    title=script_data.get("metadata", {}).get("title"),
                    description=script_data.get("metadata", {}).get("description"),
                    hashtags=script_data.get("metadata", {}).get("tags"),
                    similarity_score=script_data.get("similarity_score", 0.0)
                )
                session.add(script_asset)
                await session.commit()



            # 3. Audio Generation
            await self._update_job_state(job_id, JobState.GENERATING_AUDIO)
            audio_path = await self.audio_engine.generate_narration(script_data, job_id)
            if not audio_path:
                raise Exception("Audio generation failed")
            
            async with Database.get_session() as session:
                audio_asset = AudioAsset(
                    job_id=job_id,
                    model_name=self.audio_engine.model_name,
                    audio_path=audio_path
                )
                session.add(audio_asset)
                await session.commit()

            # 4. Visual Assembly & Rendering
            await self._update_job_state(job_id, JobState.GENERATING_VISUALS)
            # (Note: Visuals and Rendering are often combined in the engine)
            await self._update_job_state(job_id, JobState.RENDERING_DRAFT)
            video_path = await self.video_engine.assemble_video(job_id, audio_path, script_data)
            if not video_path:
                raise Exception("Video rendering failed")
            
            async with Database.get_session() as session:
                video_asset = VideoAsset(
                    job_id=job_id,
                    draft_path=video_path,
                    aspect_ratio="9:16"
                )
                session.add(video_asset)
                await session.commit()

            # 5. Awaiting Approval
            await self._update_job_state(job_id, JobState.AWAITING_APPROVAL)
            logger.info(f"Job {job_id} is ready for review.")
            return True

        except Exception as e:
            logger.error(f"Pipeline failed for job {job_id}: {e}")
            await self._update_job_state(job_id, JobState.FAILED)
            return False

    async def publish_video(self, job_id):
        """Upload an approved video to YouTube."""
        from engines.youtube_engine import YouTubeEngine
        from core.models import Channel, VideoAsset, ScriptAsset
        
        try:
            await self._update_job_state(job_id, JobState.UPLOADING)
            
            async with Database.get_session() as session:
                # 1. Fetch Job, Script (for metadata), and Video (for file path)
                result = await session.execute(
                    select(Job).where(Job.id == job_id)
                )
                job = result.scalar_one()
                
                # Fetch script and video assets
                res_s = await session.execute(select(ScriptAsset).where(ScriptAsset.job_id == job_id))
                script = res_s.scalar_one()
                
                res_v = await session.execute(select(VideoAsset).where(VideoAsset.job_id == job_id))
                video = res_v.scalar_one()

                # 2. Get YouTube credentials (assuming one channel for now)
                res_c = await session.execute(select(Channel))
                channel = res_c.scalar_one_or_none()
                
                if not channel or not channel.oauth_tokens:
                    raise Exception("No YouTube channel linked or missing tokens. Run authentication first.")

            # 3. Initialize Engine and Upload
            yt_engine = YouTubeEngine(token_data=channel.oauth_tokens)
            
            # Check if tokens were refreshed during init and save back if so
            if yt_engine.credentials and yt_engine.credentials.expired:
                 # This should have been handled in init but let's be safe
                 pass
            
            # Save potentially refreshed tokens
            await yt_engine.save_credentials(channel.channel_id, channel.user_id)

            video_id = yt_engine.upload_video(
                file_path=video.draft_path, # Or final_path if exists
                title=script.title,
                description=script.description,
                tags=script.hashtags,
                privacy_status="private" # Start as private for safety
            )

            if not video_id:
                raise Exception("YouTube upload returned no video ID")

            await self._update_job_state(job_id, JobState.UPLOADED)
            logger.info(f"Video {video_id} published for job {job_id}")
            return video_id

        except Exception as e:
            logger.error(f"Publish failed for job {job_id}: {e}")
            await self._update_job_state(job_id, JobState.FAILED)
            return None

    async def _update_job_state(self, job_id, state: JobState):
        """Helper to update job state in database."""
        async with Database.get_session() as session:
            await session.execute(
                update(Job).where(Job.id == job_id).values(state=state)
            )
            await session.commit()
            logger.info(f"Job {job_id} state updated to {state.value}")
