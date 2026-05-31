import os
import re
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
        self.script_engine = ScriptEngine()
        self.audio_engine = AudioEngine()
        self.video_engine = VideoEngine()

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
            
            metadata = script_data.get("metadata", {})
            eng_desc = metadata.get("description", "")
            hindi_title = metadata.get("hindi_title", "")
            hindi_desc = metadata.get("hindi_description", "")
            spanish_title = metadata.get("spanish_title", "")
            spanish_desc = metadata.get("spanish_description", "")

            # Combine them in a structured way for the DB description field
            combined_desc = eng_desc
            if hindi_title or hindi_desc or spanish_title or spanish_desc:
                combined_desc += "\n\n--- HINDI TRANSLATION ---\n"
                combined_desc += f"TITLE: {hindi_title}\n"
                combined_desc += f"DESC: {hindi_desc}\n"
                combined_desc += "\n--- SPANISH TRANSLATION ---\n"
                combined_desc += f"TITLE: {spanish_title}\n"
                combined_desc += f"DESC: {spanish_desc}\n"

            async with Database.get_session() as session:
                script_asset = ScriptAsset(
                    job_id=job_id,
                    topic=topic_data.get("title_en"),
                    script_text=script_data.get("narration"),
                    title=metadata.get("title"),
                    description=combined_desc,
                    hashtags=metadata.get("tags"),
                    thumbnail_text=metadata.get("thumbnail_text", "AVOID THIS MISTAKE"),
                    similarity_score=script_data.get("similarity_score", 0.0)
                )
                session.add(script_asset)
                await session.commit()

            await notify(f"✅ Script ready — Topic: {topic_data.get('title_en', 'N/A')}")

            # ===== STAGE 2: Audio Generation =====
            await self._update_job_state(job_id, JobState.GENERATING_AUDIO)
            await notify("🔊 Stage 2/4: Generating Tamil Audio Narration...")
            
            audio_path = await self.audio_engine.generate_narration(script_data, job_id)
            if not audio_path:
                await notify("❌ Audio generation failed")
                raise Exception("Audio generation failed")
            
            async with Database.get_session() as session:
                audio_asset = AudioAsset(
                    job_id=job_id,
                    model_name=getattr(self.audio_engine, "primary_model", "gemini-tts"),
                    audio_path=audio_path
                )
                session.add(audio_asset)
                await session.commit()

            await notify("✅ Audio narration generated")

            # ===== STAGE 3: Visual Asset Gathering =====
            await self._update_job_state(job_id, JobState.GENERATING_VISUALS)
            await notify("🎨 Stage 3/4: Fetching stock visuals from Pexels...")

            # ===== STAGE 4: Video Rendering =====
            await self._update_job_state(job_id, JobState.RENDERING_DRAFT)
            await notify("🎬 Stage 4/4: Rendering video with FFmpeg...")
            
            video_path = await self.video_engine.assemble_video(job_id, audio_path, script_data)
            if not video_path:
                await notify("❌ Video rendering failed — no output file")
                raise Exception("Video rendering failed")
            
            if not os.path.exists(video_path):
                await notify(f"❌ Video file not found at {video_path}")
                raise Exception(f"Video file not found at {video_path}")
            
            file_size = os.path.getsize(video_path)
            await notify(f"✅ Video rendered ({file_size // 1024}KB)")
            
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
                    
                    is_auto = False
                    if job and job.schedule and job.schedule.user.approval_mode == "auto":
                        is_auto = True
                    else:
                        res_user = await session.execute(select(User).limit(1))
                        first_user = res_user.scalar_one_or_none()
                        if first_user and first_user.approval_mode == "auto":
                            is_auto = True
                            
                    if is_auto:
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
        """Upload an approved video to YouTube with retry logic."""
        from engines.youtube_engine import YouTubeEngine
        from core.models import Channel, VideoAsset, ScriptAsset
        import asyncio as _asyncio
        
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

            # 3. Initialize Engine and Upload (with retry)
            yt_engine = YouTubeEngine(token_data=channel.oauth_tokens)
            
            # Save potentially refreshed tokens
            await yt_engine.save_credentials(channel.channel_id, channel.user_id)

            # Upload with retry logic (3 attempts, exponential backoff)
            video_id = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    video_id = yt_engine.upload_video(
                        file_path=video.draft_path,
                        title=script.title,
                        description=script.description,
                        tags=script.hashtags,
                        privacy_status="public"
                    )
                    if video_id:
                        break
                except Exception as upload_err:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s
                        logger.warning(f"Upload attempt {attempt+1}/{max_retries} failed: {upload_err}. Retrying in {wait_time}s...")
                        await _asyncio.sleep(wait_time)
                        # Re-initialize engine in case of token expiry
                        yt_engine = YouTubeEngine(token_data=channel.oauth_tokens)
                    else:
                        raise upload_err

            if not video_id:
                raise Exception("YouTube upload returned no video ID after all retries")

            # Upload Closed Captions (CC) automatically if CC mode is enabled
            if settings.SUBTITLE_MODE == "cc":
                final_srt_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_final.srt")
                if os.path.exists(final_srt_path):
                    try:
                        logger.info("Automatically uploading Closed Captions (.srt) to YouTube...")
                        yt_engine.upload_captions(video_id, final_srt_path, language="ta", name="Tamil Subtitles")
                    except Exception as ce:
                        logger.error(f"Failed to automatically upload captions: {ce}")
                else:
                    logger.warning(f"Closed Captions mode enabled, but SRT file was not found at {final_srt_path}")

            # 4. Upload Custom Thumbnail if exists
            thumbnail_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_thumbnail.jpg")
            if os.path.exists(thumbnail_path):
                try:
                    logger.info("Uploading custom thumbnail...")
                    yt_engine.upload_thumbnail(video_id, thumbnail_path)
                except Exception as te:
                    logger.error(f"Failed to upload thumbnail: {te}")

            # 5. Set Multi-Language Localizations (English + Tamil + Hindi + Spanish)
            try:
                desc = script.description or ""
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

                localizations = {
                    "en": {
                        "title": script.title or "",
                        "description": eng_desc or ""
                    },
                    "ta": {
                        "title": script.topic or script.title or "",
                        "description": eng_desc or ""
                    }
                }
                if hindi_title:
                    localizations["hi"] = {
                        "title": hindi_title,
                        "description": hindi_desc or eng_desc
                    }
                if spanish_title:
                    localizations["es"] = {
                        "title": spanish_title,
                        "description": spanish_desc or eng_desc
                    }

                yt_engine.set_video_localizations(
                    video_id=video_id,
                    localizations=localizations
                )
            except Exception as le:
                logger.warning(f"Failed to set video localizations (non-fatal): {le}")

            # 6. Post Bilingual CTA Comment (Tamil + English)
            comment_text = (
                "🇮🇳 Tamil:\n"
                "மேலும் பல சிவில் தகவல்களுக்கு Subscribe செய்யுங்கள்! "
                "உங்கள் கனவு இல்லத்திற்கு உடனே தொடர்பு கொள்ளுங்கள்!\n\n"
                "🌍 English:\n"
                "Subscribe for more civil engineering tips! "
                "Contact us for your dream home construction!\n\n"
                "📞 Call/WhatsApp: +91 83440 51846\n"
                "🌐 Website: https://kitchaas-enterprise.com/\n"
                "📷 Instagram: https://www.instagram.com/nirmal.sunjaiy369"
            )
            try:
                logger.info("Posting bilingual CTA comment to YouTube video...")
                yt_engine.post_comment(video_id, comment_text)
            except Exception as ce:
                logger.error(f"Failed to post CTA comment: {ce}")

            await self._update_job_state(job_id, JobState.UPLOADED)
            logger.info(f"Video {video_id} published for job {job_id}")
            
            # 7. Clean up old job files to prevent disk exhaustion
            self._cleanup_old_outputs(job_id)
            
            return video_id

        except Exception as e:
            logger.error(f"Publish failed for job {job_id}: {e}")
            await self._update_job_state(job_id, JobState.FAILED)
            raise e

    def _cleanup_old_outputs(self, current_job_id, keep_last=5):
        """Remove output files from old jobs, keeping only the last N jobs' files."""
        import glob
        try:
            all_files = glob.glob(os.path.join(settings.OUTPUT_DIR, "*_final.*"))
            all_files += glob.glob(os.path.join(settings.OUTPUT_DIR, "*_thumbnail.*"))
            all_files += glob.glob(os.path.join(settings.OUTPUT_DIR, "*_narration.*"))
            
            # Extract unique job IDs from filenames
            job_ids = set()
            for f in all_files:
                basename = os.path.basename(f)
                parts = basename.split("_", 1)
                if parts[0].isdigit():
                    job_ids.add(int(parts[0]))
            
            # Sort and identify old jobs to delete (keep last N + current)
            sorted_ids = sorted(job_ids, reverse=True)
            ids_to_keep = set(sorted_ids[:keep_last])
            try:
                ids_to_keep.add(int(current_job_id))
            except (ValueError, TypeError):
                pass
            
            deleted_count = 0
            for f in all_files:
                basename = os.path.basename(f)
                parts = basename.split("_", 1)
                if parts[0].isdigit() and int(parts[0]) not in ids_to_keep:
                    try:
                        os.remove(f)
                        deleted_count += 1
                    except Exception:
                        pass
            
            if deleted_count > 0:
                logger.info(f"Disk cleanup: removed {deleted_count} files from old jobs (keeping last {keep_last})")
        except Exception as e:
            logger.warning(f"Disk cleanup failed (non-fatal): {e}")

    async def _update_job_state(self, job_id, state: JobState):
        """Helper to update job state in database."""
        async with Database.get_session() as session:
            await session.execute(
                update(Job).where(Job.id == job_id).values(state=state)
            )
            await session.commit()
            logger.info(f"Job {job_id} state updated to {state.value}")
