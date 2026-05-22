import os
import logging
import asyncio
import httpx
from core.config import settings

logger = logging.getLogger(__name__)

class HeyGenEngine:
    def __init__(self):
        self.api_key = settings.HEYGEN_API_KEY
        self.live_mode = settings.HEYGEN_LIVE_MODE
        self.avatar_id = settings.HEYGEN_AVATAR_ID
        self.voice_id = settings.HEYGEN_VOICE_ID
        self.base_url = "https://api.heygen.com"
        
        logger.info(
            f"Initialized HeyGenEngine: Live Mode={self.live_mode}, "
            f"Avatar={self.avatar_id}, Voice={self.voice_id}"
        )

    async def check_credits(self) -> float:
        """Fetch the remaining HeyGen credits from user profile.
        
        Returns:
            Remaining credits as float, or 0.0 on failure/mock mode.
        """
        if not self.live_mode:
            logger.info("HeyGen [Mock Mode]: Simulating remaining credits check (100.0 credits available).")
            return 100.0

        if not self.api_key:
            logger.error("HeyGen API Key is missing. Cannot check credits.")
            return 0.0

        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # v1/user/remaining_credits endpoint is the standard credits API
                response = await client.get(f"{self.base_url}/v1/user/remaining_credits", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    credits = data.get("data", {}).get("remaining_credits", 0.0)
                    logger.info(f"HeyGen: Remaining credits: {credits}")
                    return float(credits)
                else:
                    logger.warning(f"Failed to check HeyGen credits: HTTP {response.status_code} - {response.text}")
                    return 0.0
        except Exception as e:
            logger.error(f"Error checking HeyGen credits: {e}")
            return 0.0

    async def generate_video_agent_job(self, script_text: str, visual_style_prompt: str) -> str:
        """Submit a prompt-based video generation job to HeyGen Video Agent API.
        
        Args:
            script_text: The Tamil narration script for the avatar.
            visual_style_prompt: The detailed English style guide for B-roll / visuals.
            
        Returns:
            The session_id of the generated job, or a mock session_id.
        """
        # Combine script and visual styles into the agent prompt
        agent_prompt = (
            f"Narration Script (Speak this exact text in Tamil): {script_text}\n\n"
            f"Visual and background style instructions: {visual_style_prompt}"
        )
        
        if not self.live_mode:
            logger.info("HeyGen [Mock Mode]: Simulating job submission for Video Agent.")
            logger.info(f"Mock Prompt sent to Agent:\n{agent_prompt}")
            return "mock_session_agent_12345"

        if not self.api_key:
            raise ValueError("HeyGen API Key is missing. Set HEYGEN_API_KEY in .env file.")

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "prompt": agent_prompt,
            "mode": "generate",
            "avatar_id": self.avatar_id,
            "voice_id": self.voice_id,
            "orientation": "portrait"  # Portrait mode for 9:16 Shorts
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                logger.info(f"Submitting job to HeyGen Video Agent API...")
                response = await client.post(f"{self.base_url}/v3/video-agents", headers=headers, json=payload)
                
                if response.status_code in [200, 201]:
                    data = response.json()
                    # Response can structure the ID under 'data' or directly in root
                    session_id = data.get("data", {}).get("session_id") or data.get("session_id")
                    if not session_id:
                        raise Exception(f"Session ID not found in HeyGen response: {data}")
                    logger.info(f"HeyGen: Session created successfully. Session ID: {session_id}")
                    return session_id
                else:
                    raise Exception(f"HeyGen API Error: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Failed to submit HeyGen Video Agent job: {e}")
            raise e

    async def poll_agent_status(self, session_id: str, poll_interval: int = 15, timeout: int = 600) -> str:
        """Poll the session status until the video generation is completed or failed.
        
        Args:
            session_id: The ID of the HeyGen session.
            poll_interval: Seconds to wait between polls.
            timeout: Maximum seconds to poll.
            
        Returns:
            The downloadable video URL.
        """
        if not self.live_mode:
            logger.info("HeyGen [Mock Mode]: Simulating polling progress...")
            await asyncio.sleep(2)
            logger.info("HeyGen [Mock Mode]: Status completed. Returning mock download URL.")
            return "mock_video_url_link"

        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json"
        }

        elapsed = 0
        while elapsed < timeout:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    logger.info(f"Polling HeyGen status for Session {session_id} (elapsed: {elapsed}s)...")
                    response = await client.get(f"{self.base_url}/v3/video-agents/{session_id}", headers=headers)
                    
                    if response.status_code == 200:
                        data = response.json()
                        session_data = data.get("data", {}) if "data" in data else data
                        
                        status = session_data.get("status")
                        logger.info(f"HeyGen Session {session_id} status: {status}")
                        
                        if status == "completed":
                            video_url = session_data.get("video_url")
                            if not video_url:
                                raise Exception("HeyGen reported completed, but no video_url was found.")
                            return video_url
                        elif status == "failed":
                            error_info = session_data.get("error", "Unknown error")
                            raise Exception(f"HeyGen Video Agent generation failed: {error_info}")
                    else:
                        logger.warning(f"Error polling status: HTTP {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Exception during polling: {e}")
                # We raise only if it's a generation failure, transient polling errors are retried
                if "failed" in str(e).lower():
                    raise e
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"HeyGen Video Agent generation timed out after {timeout} seconds.")

    async def download_video(self, video_url: str, output_path: str) -> bool:
        """Download the completed video to the specified path.
        
        Args:
            video_url: The URL to the video file.
            output_path: Path where the file should be saved.
            
        Returns:
            True if download succeeded, False otherwise.
        """
        if not self.live_mode:
            logger.info("HeyGen [Mock Mode]: Generating a local mockup MP4 file via FFmpeg...")
            try:
                # Generate a 5-second vertical (1080x1920) blue video with silent audio using FFmpeg
                process = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", 
                    "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=5", 
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", 
                    "-c:v", "libx264", "-t", "5", 
                    "-c:a", "aac", "-pix_fmt", "yuv420p", 
                    output_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                if process.returncode == 0 and os.path.exists(output_path):
                    logger.info(f"HeyGen [Mock Mode]: Mock video successfully created at {output_path}")
                    return True
                else:
                    logger.error(f"HeyGen [Mock Mode]: FFmpeg failed to create mock video: {stderr.decode()}")
                    return False
            except Exception as e:
                logger.error(f"HeyGen [Mock Mode]: Failed to generate mock video: {e}")
                return False

        try:
            logger.info(f"Downloading completed HeyGen video from {video_url}...")
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("GET", video_url) as response:
                    if response.status_code == 200:
                        with open(output_path, "wb") as f:
                            async for chunk in response.iter_bytes():
                                f.write(chunk)
                        logger.info(f"HeyGen video successfully saved to {output_path}")
                        return True
                    else:
                        logger.error(f"Failed to download video: HTTP {response.status_code}")
                        return False
        except Exception as e:
            logger.error(f"Error downloading HeyGen video: {e}")
            return False
