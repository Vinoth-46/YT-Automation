import os
import logging
import asyncio
import aiohttp
import traceback
from core.config import settings

logger = logging.getLogger(__name__)

class VideoEngine:
    def __init__(self):
        self.pexels_api_key = settings.PEXELS_API_KEY

    async def assemble_video(self, job_id, narration_path, script_data):
        """Orchestrate the hybrid visual assembly."""
        output_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_final.mp4")
        scenes = script_data.get("scenes", [])
        
        logger.info(f"Job {job_id}: Starting video assembly with {len(scenes)} scenes")
        
        if not scenes:
            logger.error(f"Job {job_id}: No scenes found in script_data")
            return None

        # 1. Gather Assets
        scene_assets = await self._gather_assets(job_id, scenes)
        if not scene_assets:
            logger.error(f"Job {job_id}: No visual assets gathered — cannot render video")
            return None

        logger.info(f"Job {job_id}: Gathered {len(scene_assets)} video assets, starting FFmpeg render")

        # 2. Final Render with FFmpeg
        success = await self._render_ffmpeg(scene_assets, narration_path, output_path)
        
        if success and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"Job {job_id}: Video rendered successfully ({file_size // 1024}KB)")
            return output_path
        else:
            logger.error(f"Job {job_id}: FFmpeg render failed or output file not found")
            return None

    async def _gather_assets(self, job_id, scenes):
        """Fetch stock videos from Pexels (async)."""
        assets = []
        used_video_ids = set()
        
        async with aiohttp.ClientSession() as session:
            for i, scene in enumerate(scenes):
                query = scene.get("visual_query", "civil engineering")
                logger.info(f"Job {job_id}: Scene {i+1}/{len(scenes)} — searching Pexels for '{query}'")
                
                asset_url = await self._search_pexels(session, query, used_video_ids)
                if asset_url:
                    local_path = os.path.join(settings.TEMP_DIR, f"{job_id}_scene_{i}.mp4")
                    downloaded = await self._download_file(session, asset_url, local_path)
                    if downloaded and os.path.exists(local_path):
                        file_size = os.path.getsize(local_path)
                        logger.info(f"Job {job_id}: Scene {i+1} downloaded ({file_size // 1024}KB)")
                        assets.append(local_path)
                    else:
                        logger.warning(f"Job {job_id}: Scene {i+1} download failed")
                else:
                    logger.warning(f"Job {job_id}: Scene {i+1} — no Pexels results for '{query}'")
        
        return assets

    async def _render_ffmpeg(self, scene_paths, audio_path, output_path):
        """Standardize clips, concatenate, and sync with audio using FFmpeg."""
        processed_clips = []
        concat_file = None
        concat_output = None
        
        try:
            logger.info(f"FFmpeg: Pre-processing {len(scene_paths)} clips to standard 720x1280 format...")
            
            # Step 1: Pre-process each clip individually
            for idx, p in enumerate(scene_paths):
                processed_path = p.replace(".mp4", f"_std_{idx}.mp4")
                cmd = [
                    "ffmpeg", "-y", "-i", p,
                    "-threads", "1",  # Crucial for 512MB RAM limits
                    "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=30,format=yuv420p",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                    "-max_muxing_queue_size", "1024",
                    "-an",  # Strip audio
                    processed_path
                ]
                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=180)
                
                if process.returncode == 0 and os.path.exists(processed_path):
                    processed_clips.append(processed_path)
                else:
                    logger.warning(f"FFmpeg failed to process clip {p}: {stderr.decode()[-300:]}")
            
            if not processed_clips:
                logger.error("FFmpeg: All clips failed pre-processing")
                return False

            # Step 2: Concatenate standard clips
            concat_file = output_path.replace(".mp4", "_concat.txt")
            with open(concat_file, "w") as f:
                for p in processed_clips:
                    f.write(f"file '{p.replace('\"', '')}'\n")
            
            concat_output = output_path.replace(".mp4", "_concat.mp4")
            concat_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c", "copy",  # Fast copy since they are already identical format
                concat_output
            ]
            
            logger.info(f"FFmpeg: Concatenating {len(processed_clips)} standard clips...")
            process = await asyncio.create_subprocess_exec(
                *concat_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            
            if process.returncode != 0:
                logger.error(f"FFmpeg concat failed: {stderr.decode()[-500:]}")
                return False
                
            # Step 3: Merge with audio
            logger.info(f"FFmpeg: Merging video with audio...")
            merge_cmd = [
                "ffmpeg", "-y", "-threads", "1",
                "-stream_loop", "-1",  # Loop video if shorter than audio
                "-i", concat_output,
                "-i", audio_path,
                "-c:v", "copy",  # Copy video stream directly
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",  # Stop when audio ends
                "-movflags", "+faststart",
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *merge_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=180)
            
            if process.returncode != 0:
                logger.error(f"FFmpeg merge failed: {stderr.decode()[-500:]}")
                # FFmpeg sometimes exits non-zero but still produces valid file
                if os.path.exists(output_path) and os.path.getsize(output_path) > 100 * 1024:
                    return True
                return False
                
            return True
            
        except asyncio.TimeoutError:
            logger.error("FFmpeg process timed out")
            return False
        except Exception as e:
            logger.error(f"FFmpeg render exception: {e}")
            logger.error(traceback.format_exc())
            return False
        finally:
            # Clean up temp files
            files_to_clean = processed_clips + [concat_file, concat_output]
            for f in files_to_clean:
                if f and os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

    async def _search_pexels(self, session, query, used_video_ids):
        """Search Pexels API with technical fallbacks (async)."""
        query = query.strip().lower()
        
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
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        logger.warning(f"Pexels API returned {response.status} for '{q}'")
                        continue
                    
                    data = await response.json()
                    
                    if data.get("videos"):
                        for video in data["videos"]:
                            vid_id = video.get("id")
                            if vid_id not in used_video_ids:
                                used_video_ids.add(vid_id)
                                video_files = video.get("video_files", [])
                                # Find a reasonable quality file (not too large for free tier)
                                for vf in video_files:
                                    width = vf.get("width", 0)
                                    height = vf.get("height", 0)
                                    # Prefer SD/HD instead of 4K/1080p to save FFmpeg memory
                                    if 480 <= width <= 720 or 480 <= height <= 1280:
                                        logger.info(f"Pexels match: '{q}' → video {vid_id} ({width}p)")
                                        return vf["link"]
                                # Fallback to smallest file to prevent OOM
                                if video_files:
                                    smallest = min(video_files, key=lambda x: x.get("width", 9999))
                                    logger.info(f"Pexels match (fallback smallest): '{q}' → video {vid_id} ({smallest.get('width')}p)")
                                    return smallest["link"]
            except asyncio.TimeoutError:
                logger.warning(f"Pexels timeout for query '{q}'")
            except Exception as e:
                logger.error(f"Pexels error for query '{q}': {e}")
                
        logger.warning(f"No Pexels results for '{query}' or fallbacks")
        return None

    async def _download_file(self, session, url, path):
        """Download asset locally (async with progress)."""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    logger.error(f"Download failed: HTTP {response.status} for {url[:80]}")
                    return False
                
                with open(path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
            
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return True
            return False
        except asyncio.TimeoutError:
            logger.error(f"Download timed out: {url[:80]}")
            return False
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False
