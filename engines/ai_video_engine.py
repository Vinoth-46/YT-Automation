import os
import time
import logging
import asyncio
import shutil
try:
    from gradio_client import Client
except ImportError:
    import subprocess
    import sys
    print("📦 gradio_client not found. Installing gradio_client automatically...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "gradio_client"], check=True)
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
            hf_token = getattr(settings, "HF_TOKEN", "").strip() or None
            try:
                self.ltx_client = Client(self.ltx_space_id, hf_token=hf_token)
            except Exception as e:
                logger.error(f"Failed to connect to LTX-Video Space ({self.ltx_space_id}): {e}")
                raise e
        return self.ltx_client

    def _get_wan_client(self):
        """Lazy loader for Wan 2.1 Gradio client."""
        if not self.wan_client:
            logger.info(f"Connecting to Hugging Face Gradio Space '{self.wan_space_id}'...")
            hf_token = getattr(settings, "HF_TOKEN", "").strip() or None
            try:
                self.wan_client = Client(self.wan_space_id, hf_token=hf_token)
            except Exception as e:
                logger.error(f"Failed to connect to Wan 2.1 Space ({self.wan_space_id}): {e}")
                raise e
        return self.wan_client

    def _clean_prompt(self, prompt: str) -> str:
        """Sanitize and optimize text-to-video prompt for physical adherence."""
        import re
        p = prompt.strip()
        # Remove markdown quotes or conversational prefixes
        p = re.sub(r'["\'\*\`]', '', p)
        # Remove conversational or call-to-action phrases
        p = re.sub(r'(?i)\b(subscribe|click|like and share|kitchaas enterprises|warning|mistake|avoid this|dont do this|must know)\b', '', p)
        # Strip extraneous spaces
        p = re.sub(r'\s+', ' ', p).strip()
        
        # Ensure it has a strong camera direction prefix if missing
        if not re.match(r'(?i)^(cinematic|close-up|drone|macro|wide|tracking|slow motion)', p):
            p = f"Cinematic close-up shot of {p}"
        
        # Append quality tags if missing
        if not re.search(r'(?i)(photorealistic|4k|high quality)', p):
            p = f"{p}, photorealistic, 4k, crisp details"
            
        return p

    def _generate_ltx_sync(self, prompt: str, output_path: str, height: int = 896, width: int = 512) -> str:
        """Fast synchronous text-to-video generation using LTX-Video Distilled (~15-20s)."""
        client = self._get_ltx_client()
        clean_prompt = self._clean_prompt(prompt)
        logger.info(f"Submitting LTX T2V task. Resolution: {width}x{height}, Prompt: '{clean_prompt[:70]}...'")
        
        neg_prompt = (
            "worst quality, inconsistent motion, blurry, jittery, distorted, lowres, "
            "cartoon, anime, running, walking, jumping, fitness, dancing, talking head, "
            "deformed face, disfigured, text, watermark"
        )
        
        res_output = client.predict(
            prompt=clean_prompt,
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
            ui_guidance_scale=3.0,
            improve_texture_flag=True,
            api_name="/text_to_video"
        )
        
        video_temp = None
        if isinstance(res_output, str) and os.path.exists(res_output):
            video_temp = res_output
        elif isinstance(res_output, (list, tuple)):
            for item in res_output:
                if isinstance(item, str) and os.path.exists(item):
                    video_temp = item
                    break
                elif isinstance(item, dict):
                    v_path = item.get("video") or item.get("path") or item.get("name")
                    if v_path and os.path.exists(v_path):
                        video_temp = v_path
                        break
        elif isinstance(res_output, dict):
            video_temp = res_output.get("video") or res_output.get("path") or res_output.get("name")
            
        if video_temp and os.path.exists(video_temp):
            logger.info(f"LTX Video generated successfully ({width}x{height}): {video_temp}")
            shutil.copy(video_temp, output_path)
            return output_path
                
        raise Exception(f"LTX-Video returned unparseable result: {res_output}")

    def _generate_wan_sync(self, prompt: str, output_path: str, size: str = "720*1280") -> str:
        """Fallback Wan 2.1 video generation via Gradio API client."""
        client = self._get_wan_client()
        clean_prompt = self._clean_prompt(prompt)
        logger.info(f"Submitting Wan 2.1 T2V task. Size: {size}, Prompt: '{clean_prompt[:70]}...'")
        
        submission = client.predict(
            prompt=clean_prompt,
            size=size,
            watermark_wan=False,
            seed=-1,
            api_name="/t2v_generation_async"
        )
        
        max_attempts = 35
        poll_interval = 8
        
        for attempt in range(max_attempts):
            time.sleep(poll_interval)
            try:
                status = client.predict(api_name="/status_refresh")
                if not status:
                    continue
                    
                # Inspect all return values in status tuple/list to locate valid MP4 file path
                items_to_check = status if isinstance(status, (list, tuple)) else [status]
                for item in items_to_check:
                    if isinstance(item, str) and os.path.exists(item) and item.endswith(".mp4"):
                        logger.info(f"Wan 2.1 Video downloaded (path: {item})")
                        shutil.copy(item, output_path)
                        return output_path
                    elif isinstance(item, dict):
                        for key in ["video", "path", "name", "url", "file", "value"]:
                            v_path = item.get(key)
                            if isinstance(v_path, str) and os.path.exists(v_path) and v_path.endswith(".mp4"):
                                logger.info(f"Wan 2.1 Video downloaded (key '{key}': {v_path})")
                                shutil.copy(v_path, output_path)
                                return output_path
                            elif isinstance(v_path, dict):
                                nested = v_path.get("path") or v_path.get("name") or v_path.get("url")
                                if isinstance(nested, str) and os.path.exists(nested) and nested.endswith(".mp4"):
                                    logger.info(f"Wan 2.1 Video downloaded (nested '{key}': {nested})")
                                    shutil.copy(nested, output_path)
                                    return output_path
            except Exception as e:
                logger.warning(f"Wan 2.1 poll warning (attempt {attempt+1}): {e}")
                
        raise Exception("Wan 2.1 AI video generation timed out or failed.")

    def _generate_nvidia_sync(self, prompt: str, output_path: str) -> str:
        """Generate video clip using NVIDIA Cosmos NIM API."""
        api_key = getattr(settings, "NVIDIA_API_KEY", "").strip()
        if not api_key:
            raise Exception("No NVIDIA_API_KEY configured in environment.")
            
        clean_prompt = self._clean_prompt(prompt)
        logger.info(f"Submitting NVIDIA Cosmos T2V task. Prompt: '{clean_prompt[:70]}...'")
        import httpx
        
        url = "https://ai.api.nvidia.com/v1/genai/nvidia/cosmos-1.0-diffusion-7b"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
        payload = {
            "prompt": clean_prompt,
            "negative_prompt": "blurry, worst quality, distorted, low quality, running, jumping, walking, cartoon, text",
            "guidance_scale": 7.0
        }
        
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                video_url = data.get("video") or data.get("video_url") or data.get("artifacts", [{}])[0].get("url")
                if video_url:
                    vid_resp = client.get(video_url)
                    if vid_resp.status_code == 200:
                        with open(output_path, "wb") as f:
                            f.write(vid_resp.content)
                        logger.info(f"NVIDIA Cosmos video saved: {output_path}")
                        return output_path
                raise Exception(f"NVIDIA API response contained no video URL: {data}")
            else:
                raise Exception(f"NVIDIA API error (HTTP {resp.status_code}): {resp.text[:200]}")

    async def generate_scene_clip(self, prompt: str, job_id: int, scene_idx: int) -> str:
        """Asynchronously generates an AI clip matching the scene script.
        Order of attempt:
        1. LTX-Video Distilled (Ultra-fast, ~15-20s, portrait 512x896)
        2. NVIDIA Cosmos 1.0 Diffusion (if NVIDIA_API_KEY configured)
        3. Wan 2.1 (720x1280 fallback)
        """
        output_filename = f"{job_id}_scene_{scene_idx}_ai.mp4"
        output_path = os.path.join(settings.TEMP_DIR, output_filename)
        
        # 1. Try LTX-Video Distilled (Ultra-fast!)
        try:
            logger.info(f"Job {job_id} Scene {scene_idx+1}: Generating video clip via LTX-Video Distilled...")
            result = await asyncio.to_thread(self._generate_ltx_sync, prompt, output_path, 896, 512)
            if result and os.path.exists(result):
                return result
        except Exception as e:
            logger.warning(f"Job {job_id} Scene {scene_idx+1}: LTX-Video failed: {e}.")

        # 2. Try NVIDIA Cosmos NIM API (if key available)
        nvidia_key = getattr(settings, "NVIDIA_API_KEY", "").strip()
        if nvidia_key:
            try:
                logger.info(f"Job {job_id} Scene {scene_idx+1}: Generating video clip via NVIDIA Cosmos...")
                result = await asyncio.to_thread(self._generate_nvidia_sync, prompt, output_path)
                if result and os.path.exists(result):
                    return result
            except Exception as ne:
                logger.warning(f"Job {job_id} Scene {scene_idx+1}: NVIDIA Cosmos failed: {ne}.")
            
        # 3. Try Wan 2.1 fallback
        try:
            logger.info(f"Job {job_id} Scene {scene_idx+1}: Generating video clip via Wan 2.1 fallback...")
            result = await asyncio.to_thread(self._generate_wan_sync, prompt, output_path, "720*1280")
            if result and os.path.exists(result):
                return result
        except Exception as e:
            logger.warning(f"Job {job_id} Scene {scene_idx+1}: Wan 2.1 fallback failed: {e}.")
            
        return None
