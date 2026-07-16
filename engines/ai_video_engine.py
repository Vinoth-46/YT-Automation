import os
import time
import logging
import asyncio
import shutil
from gradio_client import Client
from core.config import settings

logger = logging.getLogger(__name__)

class AIVideoEngine:
    def __init__(self):
        self.space_id = "Wan-AI/Wan2.1"
        self.client = None

    def _get_client(self):
        """Lazy loader for Gradio client."""
        if not self.client:
            logger.info(f"Connecting to Hugging Face Gradio Space '{self.space_id}'...")
            self.client = Client(self.space_id)
        return self.client

    def _generate_video_sync(self, prompt: str, output_path: str, size: str = "720*1280") -> str:
        """Synchronous implementation of Wan 2.1 video generation via Gradio API client."""
        client = self._get_client()
        logger.info(f"Submitting AI T2V generation task. Size: {size}, Prompt: '{prompt[:60]}...'")
        
        # Submit async task to the Space
        submission = client.predict(
            prompt=prompt,
            size=size,
            watermark_wan=False,
            seed=-1,
            api_name="/t2v_generation_async"
        )
        logger.info(f"Task submitted. Submission response: {submission}")
        
        # Poll status_refresh until complete
        max_attempts = 180
        poll_interval = 8
        logger.info("Polling Gradio space status_refresh until complete...")
        
        for attempt in range(max_attempts):
            time.sleep(poll_interval)
            try:
                status = client.predict(api_name="/status_refresh")
                # Expected status tuple: (generated_video, cost_timesecs, estimated_waiting_timesecs, progress)
                # generated_video: dict(video: filepath, subtitles: filepath | None) or None
                video_info = status[0]
                progress = status[3] if len(status) > 3 else 0
                
                logger.info(f"Generation Progress: {progress}% (Attempt {attempt+1}/{max_attempts})")
                
                if video_info is not None:
                    video_temp_path = video_info.get("video")
                    if video_temp_path and os.path.exists(video_temp_path):
                        logger.info(f"AI Video downloaded successfully to Gradio cache: {video_temp_path}")
                        # Copy from Gradio cache to our designated output path
                        shutil.copy(video_temp_path, output_path)
                        return output_path
                
                if progress == 100 and video_info is None:
                    logger.warning("Generation finished but no video path was returned.")
                    break
                    
            except Exception as e:
                logger.error(f"Error during status poll: {e}")
                
        raise Exception("AI video generation timed out or failed on Hugging Face Space.")

    async def generate_scene_clip(self, prompt: str, job_id: int, scene_idx: int) -> str:
        """Asynchronously triggers video generation on a separate thread to avoid blocking loop."""
        output_filename = f"{job_id}_scene_{scene_idx}_ai.mp4"
        output_path = os.path.join(settings.TEMP_DIR, output_filename)
        
        # Try custom portrait sizes first, fallback to square/landscape if needed
        sizes_to_try = ["720*1280", "832*1088", "960*960", "1280*720"]
        
        for size in sizes_to_try:
            try:
                # Wrap the synchronous Gradio call in asyncio.to_thread
                result = await asyncio.to_thread(self._generate_video_sync, prompt, output_path, size)
                if result and os.path.exists(result):
                    return result
            except Exception as e:
                logger.warning(f"Wan 2.1 generation failed for size {size}: {e}. Trying next fallback...")
                
        return None
