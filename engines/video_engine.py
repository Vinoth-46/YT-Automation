import os
import requests
import logging
import ffmpeg
from core.config import settings

logger = logging.getLogger(__name__)

class VideoEngine:
    def __init__(self):
        self.pexels_api_key = settings.PEXELS_API_KEY

    def search_videos(self, query, per_page=1):
        """Search Pexels for relevant background clips."""
        url = f"https://api.pexels.com/videos/search?query={query}&per_page={per_page}&orientation=portrait"
        headers = {"Authorization": self.pexels_api_key}
        
        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            if data["videos"]:
                # Pick the highest quality portrait video
                video = data["videos"][0]
                video_files = video["video_files"]
                # Filter for mobile/vertical
                vertical_files = [f for f in video_files if f["width"] < f["height"]]
                return vertical_files[0]["link"] if vertical_files else video_files[0]["link"]
        except Exception as e:
            logger.error(f"Pexels search failed: {e}")
        return None

    async def download_asset(self, url, output_path):
        """Download a video or image asset."""
        try:
            response = requests.get(url, stream=True)
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return output_path
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

    async def assemble_video(self, job_id, narration_path, script_data):
        """Assemble the final video using FFmpeg."""
        output_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_final.mp4")
        scenes = script_data.get("scenes", [])
        
        # Download background clips for each scene
        scene_assets = []
        for i, scene in enumerate(scenes):
            query = scene.get("visual_query", "civil engineering construction")
            video_url = self.search_videos(query)
            if video_url:
                asset_path = os.path.join(settings.TEMP_DIR, f"{job_id}_scene_{i}.mp4")
                await self.download_asset(video_url, asset_path)
                scene_assets.append(asset_path)

        if not scene_assets:
            logger.error("No visual assets found.")
            return None

        try:
            # Basic FFmpeg assembly (Simplification for MVP)
            # 1. Combine scenes
            # 2. Add audio
            # 3. Add text overlays
            
            # For now, let's just take the first clip and loop/stretch it to narration length
            # (In a real implementation, we'd concatenate and trim)
            input_video = ffmpeg.input(scene_assets[0])
            input_audio = ffmpeg.input(narration_path)
            
            (
                ffmpeg
                .output(input_video, input_audio, output_path, vcodec='libx264', acodec='aac', shortest=None)
                .overwrite_output()
                .run()
            )
            
            return output_path
        except Exception as e:
            logger.error(f"FFmpeg assembly failed: {e}")
            return None
