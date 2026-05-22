import os
import logging
import traceback
from datetime import datetime
from sqlalchemy import select, update
from core.config import settings
from core.database import Database
from core.models import Job, JobState, ScriptAsset, AudioAsset, VideoAsset

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self):
        from engines.script_engine import ScriptEngine
        from engines.audio_engine import AudioEngine
        from engines.video_engine import VideoEngine
        from engines.heygen_engine import HeyGenEngine
        self.script_engine = ScriptEngine()
        self.audio_engine = AudioEngine()
        self.video_engine = VideoEngine()
        self.heygen_engine = HeyGenEngine()

    async def create_job(self, schedule_id=None, planned_date=None, custom_topic=None):
        """Create a new job record in the database."""
        async with Database.get_session() as session:
            job = Job(
                schedule_id=schedule_id,
                planned_date=planned_date or datetime.now(),
                state=JobState.SCHEDULED,
                custom_topic=custom_topic
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job.id

    async def run_pipeline(self, job_id, progress_callback=None):
        """Execute the full lifecycle for a job with progress callbacks.
        
        Args:
            job_id: The job ID to process
            progress_callback: Optional async function(stage_text) for real-time updates
        """
        async def notify(text):
            """Send progress update if callback is provided."""
            logger.info(f"Job {job_id}: {text}")
            if progress_callback:
                try:
                    await progress_callback(text)
                except Exception as e:
                    logger.warning(f"Progress callback failed: {e}")

        try:
            # ===== STAGE 1: Script Generation =====
            await self._update_job_state(job_id, JobState.GENERATING_SCRIPT)
            await notify("📝 Stage 1/4: Generating AI Script & Visual Keywords...")
            
            # Fetch Job to check for a custom topic/prompt
            async with Database.get_session() as session:
                res_job = await session.execute(select(Job).where(Job.id == job_id))
                job_rec = res_job.scalar_one_or_none()
                custom_topic = job_rec.custom_topic if job_rec else None

            # Fetch past topics for exclusion (Checking last 50 for uniqueness)
            async with Database.get_session() as session:
                res = await session.execute(select(ScriptAsset.topic).order_by(ScriptAsset.id.desc()).limit(50))
                existing_topics = res.scalars().all()

            # Mega-Prompt Call
            full_data = await self.script_engine.generate_full_content(existing_topics, custom_topic=custom_topic)
            if not full_data:
                await notify("❌ Script generation failed — AI returned no content")
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
                    thumbnail_text=script_data.get("metadata", {}).get("thumbnail_text", "AVOID THIS MISTAKE"),
                    similarity_score=script_data.get("similarity_score", 0.0)
                )
                session.add(script_asset)
                await session.commit()

            await notify(f"✅ Script ready — Topic: {topic_data.get('title_en', 'N/A')}")

            # ===== STAGE 2: HeyGen Video Generation Initialization =====
            await self._update_job_state(job_id, JobState.GENERATING_AUDIO)
            await notify("🔊 Stage 2/4: Checking HeyGen credits & submitting job...")
            
            # Pre-flight credit check
            credits = await self.heygen_engine.check_credits()
            await notify(f"HeyGen remaining credits: {credits}")
            if credits < 1.0:
                await notify(f"❌ HeyGen credits insufficient: {credits} remaining")
                raise Exception(f"Insufficient HeyGen credits: {credits}")
                
            # Submit Video Agent job
            session_id = await self.heygen_engine.generate_video_agent_job(
                script_text=script_data.get("narration"),
                visual_style_prompt=script_data.get("visual_style_prompt")
            )
            
            # Save placeholder AudioAsset so DB relations/logs aren't broken
            async with Database.get_session() as session:
                audio_asset = AudioAsset(
                    job_id=job_id,
                    model_name=f"heygen-{settings.HEYGEN_VOICE_ID}",
                    audio_path=f"heygen_session_{session_id}"
                )
                session.add(audio_asset)
                await session.commit()

            await notify(f"✅ HeyGen job submitted. Session ID: {session_id}")

            # ===== STAGE 3: HeyGen Polling =====
            await self._update_job_state(job_id, JobState.GENERATING_VISUALS)
            await notify("🎨 Stage 3/4: Polling HeyGen AI video generation progress...")
            
            video_url = await self.heygen_engine.poll_agent_status(session_id)
            await notify("✅ HeyGen video generated successfully on cloud")

            # ===== STAGE 4: Download & Thumbnail Generation =====
            await self._update_job_state(job_id, JobState.RENDERING_DRAFT)
            await notify("🎬 Stage 4/4: Downloading HeyGen video & extracting thumbnail...")
            
            video_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_final.mp4")
            
            # Download the final video (mock downloads a 5s blue video if live_mode is False)
            download_success = await self.heygen_engine.download_video(video_url, video_path)
            if not download_success:
                await notify("❌ Video download/mock generation failed")
                raise Exception("HeyGen video download failed")
            
            if not os.path.exists(video_path):
                await notify(f"❌ Video file not found at {video_path}")
                raise Exception(f"Video file not found at {video_path}")
                
            # Extract thumbnail frame from downloaded MP4 using Pillow-based overlay
            thumbnail_text = script_data.get("metadata", {}).get("thumbnail_text", "AVOID THIS MISTAKE")
            thumbnail_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_thumbnail.jpg")
            try:
                self.video_engine.generate_thumbnail(video_path, thumbnail_path, thumbnail_text)
                await notify("✅ Custom Oswald-Bold thumbnail generated")
            except Exception as te:
                logger.error(f"Job {job_id}: Failed to generate thumbnail: {te}")
                await notify("⚠️ Thumbnail generation failed (non-fatal)")
            
            file_size = os.path.getsize(video_path)
            await notify(f"✅ Video downloaded and processed ({file_size // 1024}KB)")
            
            async with Database.get_session() as session:
                video_asset = VideoAsset(
                    job_id=job_id,
                    draft_path=video_path,
                    aspect_ratio="9:16"
                )
                session.add(video_asset)
                await session.commit()

            # ===== DONE =====
            await self._update_job_state(job_id, JobState.AWAITING_APPROVAL)
            
            # Check for Auto-Approval
            try:
                async with Database.get_session() as session:
                    from sqlalchemy.orm import selectinload
                    from core.models import User, Schedule
                    
                    # Fetch job with user details
                    res = await session.execute(
                        select(Job).options(
                            selectinload(Job.schedule).selectinload(Schedule.user)
                        ).where(Job.id == job_id)
                    )
                    job = res.scalar_one_or_none()
                    
                    if job and job.schedule and job.schedule.user.approval_mode == "auto":
                        await notify("🚀 Auto-Approval detected! Starting YouTube upload...")
                        await self.publish_video(job_id)
                        await notify("✅ Video automatically published to YouTube!")
                    else:
                        await notify("✅ Video ready for review!")
            except Exception as e:
                logger.warning(f"Auto-approval check failed: {e}")
                await notify("✅ Video ready for review (Auto-approval check failed)")

            logger.info(f"Job {job_id} processing complete.")
            return True

        except Exception as e:
            logger.error(f"Pipeline failed for job {job_id}: {e}")
            logger.error(traceback.format_exc())
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
                
                # Fetch LATEST script and video assets (job may have been regenerated)
                res_s = await session.execute(
                    select(ScriptAsset).where(ScriptAsset.job_id == job_id)
                    .order_by(ScriptAsset.id.desc()).limit(1)
                )
                script = res_s.scalar_one_or_none()
                if not script:
                    raise Exception(f"No script asset found for job {job_id}")

                res_v = await session.execute(
                    select(VideoAsset).where(VideoAsset.job_id == job_id)
                    .order_by(VideoAsset.id.desc()).limit(1)
                )
                video = res_v.scalar_one_or_none()
                if not video:
                    raise Exception(f"No video asset found for job {job_id}")

                # 2. Get YouTube credentials (assuming one channel for now)
                res_c = await session.execute(select(Channel))
                channel = res_c.scalar_one_or_none()
                
                if not channel or not channel.oauth_tokens:
                    raise Exception("No YouTube channel linked or missing tokens. Run authentication first.")

            # 3. Initialize Engine and Upload
            yt_engine = YouTubeEngine(token_data=channel.oauth_tokens)
            
            # Save potentially refreshed tokens
            await yt_engine.save_credentials(channel.channel_id, channel.user_id)

            video_id = yt_engine.upload_video(
                file_path=video.draft_path,
                title=script.title,
                description=script.description,
                tags=script.hashtags,
                privacy_status="public"
            )

            if not video_id:
                raise Exception("YouTube upload returned no video ID")

            # 4. Upload Custom Thumbnail if exists
            thumbnail_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_thumbnail.jpg")
            if os.path.exists(thumbnail_path):
                try:
                    logger.info("Uploading custom thumbnail...")
                    yt_engine.upload_thumbnail(video_id, thumbnail_path)
                except Exception as te:
                    logger.error(f"Failed to upload thumbnail: {te}")

            # 5. Post Pinned-style CTA Comment
            comment_text = (
                "மேலும் பல சிவில் தகவல்களுக்கு Subscribe செய்யுங்கள்! "
                "உங்கள் கனவு இல்லத்திற்கு உடனே தொடர்பு கொள்ளுங்கள்:\n"
                "📞 Call/WhatsApp: +91 83440 51846\n"
                "🌐 Website: https://kitchaas-enterprise.com/\n"
                "📷 Instagram: https://www.instagram.com/nirmal.sunjaiy369"
            )
            try:
                logger.info("Posting CTA comment to YouTube video...")
                yt_engine.post_comment(video_id, comment_text)
            except Exception as ce:
                logger.error(f"Failed to post CTA comment: {ce}")

            await self._update_job_state(job_id, JobState.UPLOADED)
            logger.info(f"Video {video_id} published for job {job_id}")
            return video_id

        except Exception as e:
            logger.error(f"Publish failed for job {job_id}: {e}")
            await self._update_job_state(job_id, JobState.FAILED)
            raise e

    async def _update_job_state(self, job_id, state: JobState):
        """Helper to update job state in database."""
        async with Database.get_session() as session:
            await session.execute(
                update(Job).where(Job.id == job_id).values(state=state)
            )
            await session.commit()
            logger.info(f"Job {job_id} state updated to {state.value}")
