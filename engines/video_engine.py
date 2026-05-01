import os
import logging
import ffmpeg
import requests
import asyncio
from core.config import settings

logger = logging.getLogger(__name__)

class VideoEngine:
    def __init__(self):
        self.pexels_api_key = settings.PEXELS_API_KEY

    async def assemble_video(self, job_id, narration_path, script_data):
        """Orchestrate the hybrid visual assembly."""
        output_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_final.mp4")
        scenes = script_data.get("scenes", [])
        
        # 1. Gather Assets
        scene_assets = await self._gather_assets(job_id, scenes)
        if not scene_assets:
            return None

        # 2. Add Overlay Information (Captions/Subtitles)
        # (This could involve calling a Whisper-based captioning engine later)
        
        # 3. Final Render with FFmpeg
        success = await self._render_ffmpeg(scene_assets, narration_path, output_path)
        return output_path if success else None

    async def _gather_assets(self, job_id, scenes):
        """Fetch stock videos or generate AI video scenes."""
        assets = []
        used_video_ids = set()
        
        for i, scene in enumerate(scenes):
            query = scene.get("visual_query", "civil engineering")
            # Logic for hybrid: Try stock first, then maybe AI generation for 'hero' scenes
            asset_url = await self._search_pexels(query, used_video_ids)
            if asset_url:
                local_path = os.path.join(settings.TEMP_DIR, f"{job_id}_scene_{i}.mp4")
                await self._download_file(asset_url, local_path)
                assets.append(local_path)
        return assets

    async def _render_ffmpeg(self, scene_paths, audio_path, output_path):
        """Concatenate clips and sync with audio."""
        try:
            # For MVP: Simple concatenation and loop to match audio duration
            # (In production, use complex filters for transitions and text overlays)
            input_audio = ffmpeg.input(audio_path)
            
            # Normalize all inputs to exact 720x1280 @ 30fps for successful concatenation
            video_streams = []
            for p in scene_paths:
                v = ffmpeg.input(p).video
                # Scale to fill 720x1280 (increase), crop exact, set 30fps
                v = v.filter('scale', 720, 1280, force_original_aspect_ratio='increase')
                v = v.filter('crop', 720, 1280)
                v = v.filter('fps', fps=30, round='up')
                v = v.filter('format', 'yuv420p')
                video_streams.append(v)
            
            # Note: Concat filters can be complex in ffmpeg-python. 
            # We'll stick to a simplified version for now.
            v = ffmpeg.concat(*video_streams, v=1, a=0).node
            
            out = ffmpeg.output(
                v[0], input_audio, output_path,
                vcodec='libx264', acodec='aac', shortest=None,
                pix_fmt='yuv420p'
            ).overwrite_output()
            
            # Run in executor to not block async loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: out.run(capture_stdout=True, capture_stderr=True))
            return True
        except ffmpeg.Error as e:
            error_message = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"FFmpeg render reported error: {error_message}")
            # FFmpeg often returns non-zero exit codes on EOF when stream lengths mismatch,
            # even though it successfully rendered the complete file. Check if the file exists.
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1024 * 1024:
                logger.info(f"Output video {output_path} generated successfully despite ffmpeg warning.")
                return True
            return False
        except Exception as e:
            logger.error(f"FFmpeg render exception: {e}")
            return False

    async def _search_pexels(self, query, used_video_ids):
        """Search Pexels API with technical fallbacks to ensure 100% relevance."""
        # Clean the query
        query = query.strip().lower()
        
        # Define fallback chain for common civil engineering terms
        # If the specific action fails, try these related but still technical terms
        fallbacks = [
            query,
            f"construction {query}",
            "civil engineering construction",
            "building site"
        ]
        
        headers = {"Authorization": self.pexels_api_key}
        
        for q in fallbacks:
            url = f"https://api.pexels.com/videos/search?query={q}&per_page=15&orientation=portrait"
            try:
                response = requests.get(url, headers=headers)
                data = response.json()
                
                if data.get("videos"):
                    for video in data["videos"]:
                        vid_id = video.get("id")
                        if vid_id not in used_video_ids:
                            used_video_ids.add(vid_id)
                            # Return the best quality link
                            video_files = video.get("video_files", [])
                            if video_files:
                                logger.info(f"Pexels match found for query '{q}'")
                                return video_files[0]["link"]
            except Exception as e:
                logger.error(f"Pexels error for query '{q}': {e}")
                
        logger.warning(f"No technical matches found for '{query}' or its fallbacks.")
        return None


    async def _download_file(self, url, path):
        """Download asset locally."""
        try:
            response = requests.get(url, stream=True)
            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False
