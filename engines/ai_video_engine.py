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
        self.ltx_space_id = "Lightricks/ltx-video-distilled"
        self.wan_space_id = "Wan-AI/Wan2.1"
        self.ltx_client = None
        self.wan_client = None

    def _get_ltx_client(self):
        """Lazy loader for LTX-Video Gradio client (Fastest, ~15-20 sec)."""
        if not self.ltx_client:
            logger.info(f"Connecting to Lightricks LTX-Video Space '{self.ltx_space_id}'...")
            self.ltx_client = Client(self.ltx_space_id)
        return self.ltx_client

    def _get_wan_client(self):
        """Lazy loader for Wan 2.1 Gradio client."""
        if not self.wan_client:
            logger.info(f"Connecting to Hugging Face Gradio Space '{self.wan_space_id}'...")
            self.wan_client = Client(self.wan_space_id)
        return self.wan_client

    def _generate_ltx_sync(self, prompt: str, output_path: str, height: int = 896, width: int = 512) -> str:
        """Fast synchronous text-to-video generation using LTX-Video Distilled (~15-20s)."""
        client = self._get_ltx_client()
        logger.info(f"Submitting LTX T2V task. Resolution: {width}x{height}, Prompt: '{prompt[:60]}...'")
        
        neg_prompt = "worst quality, inconsistent motion, blurry, jittery, distorted, lowres"
        
        result, seed = client.predict(
            prompt=prompt,
            negative_prompt=neg_prompt,
            input_image_filepath=None,
            input_video_filepath=None,
            height_ui=height,
            width_ui=width,
            mode="text-to-video",
            duration_ui=3,
            ui_frames_to_use=9,
            seed_ui=42,
            randomize_seed=True,
            ui_guidance_scale=1,
            improve_texture_flag=True,
            api_name="/text_to_video"
        )
        
        if result and isinstance(result, dict) and result.get("video"):
            video_temp = result.get("video")
            if os.path.exists(video_temp):
                logger.info(f"LTX Video generated successfully ({width}x{height}): {video_temp}")
                shutil.copy(video_temp, output_path)
                return output_path
                
        raise Exception("LTX-Video returned no video filepath.")

    def _generate_wan_sync(self, prompt: str, output_path: str, size: str = "720*1280") -> str:
        """Fallback Wan 2.1 video generation via Gradio API client."""
        client = self._get_wan_client()
        logger.info(f"Submitting Wan 2.1 T2V task. Size: {size}, Prompt: '{prompt[:60]}...'")
        
        submission = client.predict(
            prompt=prompt,
            size=size,
            watermark_wan=False,
            seed=-1,
            api_name="/t2v_generation_async"
        )
        
        max_attempts = 30
        poll_interval = 8
        
        for attempt in range(max_attempts):
            time.sleep(poll_interval)
            try:
                status = client.predict(api_name="/status_refresh")
                video_info = status[0] if status else None
                progress = status[3] if len(status) > 3 else 0
                
                logger.info(f"Wan 2.1 Progress: {progress}% (Attempt {attempt+1}/{max_attempts})")
                
                if video_info is not None:
                    video_temp_path = video_info.get("video")
                    if video_temp_path and os.path.exists(video_temp_path):
                        logger.info(f"Wan 2.1 Video downloaded: {video_temp_path}")
                        shutil.copy(video_temp_path, output_path)
                        return output_path
                
                if progress == 100 and video_info is None:
                    break
            except Exception as e:
                logger.warning(f"Wan 2.1 poll warning: {e}")
                
        raise Exception("Wan 2.1 AI video generation timed out or failed.")

    async def generate_scene_clip(self, prompt: str, job_id: int, scene_idx: int) -> str:
        """Asynchronously generates an AI clip.
        Order of attempt:
        1. LTX-Video Distilled (Ultra-fast, ~15-20s, portrait 512x896)
        2. Wan 2.1 (720x1280 fallback)
        """
        output_filename = f"{job_id}_scene_{scene_idx}_ai.mp4"
        output_path = os.path.join(settings.TEMP_DIR, output_filename)
        
        # 1. Try LTX-Video Distilled first (Ultra-fast!)
        try:
            logger.info(f"Job {job_id} Scene {scene_idx+1}: Trying LTX-Video Distilled (Primary AI Generator)...")
            result = await asyncio.to_thread(self._generate_ltx_sync, prompt, output_path, 896, 512)
            if result and os.path.exists(result):
                return result
        except Exception as e:
            logger.warning(f"Job {job_id} Scene {scene_idx+1}: LTX-Video failed: {e}. Trying Wan 2.1 fallback...")
            
        # 2. Try Wan 2.1 fallback
        try:
            logger.info(f"Job {job_id} Scene {scene_idx+1}: Trying Wan 2.1 fallback...")
            result = await asyncio.to_thread(self._generate_wan_sync, prompt, output_path, "720*1280")
            if result and os.path.exists(result):
                return result
        except Exception as e:
            logger.warning(f"Job {job_id} Scene {scene_idx+1}: Wan 2.1 fallback failed: {e}.")
            
        return None
