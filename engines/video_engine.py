import os
import logging
import asyncio
import aiohttp
import httpx
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
        
    async def _generate_srt(self, audio_path, srt_path):
        """Use Groq Whisper API to generate an SRT file with 1-word fast subtitles."""
        groq_api_key = settings.GROQ_API_KEY
        if not groq_api_key:
            logger.warning("GROQ_API_KEY not found. Skipping dynamic subtitles.")
            return False
            
        try:
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {groq_api_key}"}
            
            with open(audio_path, "rb") as f:
                files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
                data = {
                    "model": "whisper-large-v3",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word"
                }
                
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, headers=headers, files=files, data=data, timeout=60.0)
                    
            if resp.status_code != 200:
                logger.error(f"Groq API error: {resp.text}")
                return False
                
            result = resp.json()
            words = result.get("words", [])
            
            if not words:
                logger.warning("Groq API returned no words.")
                return False
                
            # Convert to SRT
            def format_time(seconds):
                ms = int((seconds % 1) * 1000)
                m, s = divmod(int(seconds), 60)
                h, m = divmod(m, 60)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                
            with open(srt_path, "w", encoding="utf-8") as f:
                for i, word_data in enumerate(words):
                    start = format_time(word_data["start"])
                    end = format_time(word_data["end"])
                    word = word_data["word"].strip()
                    f.write(f"{i+1}\n{start} --> {end}\n{word}\n\n")
                    
            logger.info(f"Generated SRT with {len(words)} words.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to generate SRT: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    async def _render_ffmpeg(self, scene_paths, audio_path, output_path):
        """Standardize clips, concatenate, and sync with audio using FFmpeg."""
        job_id = os.path.basename(audio_path).split('_')[0]
        temp_dir = os.path.dirname(audio_path) or settings.TEMP_DIR
        
        processed_clips = []
        concat_file = None
        concat_output = None
        
        try:
            logger.info(f"FFmpeg: Pre-processing {len(scene_paths)} clips to standard 720x1280 format...")
            
            # Step 1: Pre-process each clip individually
            watermark_path = os.path.join(os.getcwd(), "assets", "Watermark", "loading-logo.webp")
            has_watermark = os.path.exists(watermark_path)
            logger.info(f"Job {job_id}: Watermark found: {has_watermark} at {watermark_path}")
            
            for idx, p in enumerate(scene_paths):
                processed_path = p.replace(".mp4", f"_std_{idx}.mp4")
                if has_watermark:
                    cmd = [
                        "ffmpeg", "-y", "-i", p,
                        "-i", watermark_path,
                        "-threads", "1",
                        "-filter_complex", "[0:v]scale=480:854:force_original_aspect_ratio=increase,crop=480:854,fps=30,format=yuv420p[bg];[1:v]scale=100:-1[wm];[bg][wm]overlay=W-w-15:15",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",
                        "-max_muxing_queue_size", "1024",
                        "-an",  # Strip audio
                        processed_path
                    ]
                else:
                    cmd = [
                        "ffmpeg", "-y", "-i", p,
                        "-threads", "1",
                        "-vf", "scale=480:854:force_original_aspect_ratio=increase,crop=480:854,fps=30,format=yuv420p",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",
                        "-max_muxing_queue_size", "1024",
                        "-an",
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
                
            import glob
            import random
            
            # Get audio duration
            probe_cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", audio_path
            ]
            process = await asyncio.create_subprocess_exec(*probe_cmd, stdout=asyncio.subprocess.PIPE)
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30)
            audio_duration = float(stdout.decode().strip())
            
            cta_duration = 6.0
            main_duration = max(0.0, audio_duration - cta_duration)
            
            # Check for CTA images
            cta_images = glob.glob("assets/cta_images/*")
            cta_image = random.choice(cta_images) if cta_images else None
            
            files_to_clean = processed_clips + [concat_file, concat_output]
            final_concat_list = os.path.join(temp_dir, f"{job_id}_final_list.txt")
            files_to_clean.append(final_concat_list)
            
            if cta_image and main_duration > 0:
                logger.info(f"Job {job_id}: Appending CTA image {os.path.basename(cta_image)}")
                
                # 1. Trim looped Pexels video to main_duration
                main_video_mp4 = os.path.join(temp_dir, f"{job_id}_main.mp4")
                files_to_clean.append(main_video_mp4)
                
                main_cmd = [
                    "ffmpeg", "-y", "-threads", "1",
                    "-stream_loop", "-1", "-i", concat_output,
                    "-t", str(main_duration), "-c:v", "copy",
                    main_video_mp4
                ]
                logger.info(f"FFmpeg: Trimming main video to {main_duration}s...")
                proc_main = await asyncio.create_subprocess_exec(*main_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr = await asyncio.wait_for(proc_main.communicate(), timeout=60)
                if proc_main.returncode != 0:
                    logger.error(f"FFmpeg main trim failed: {stderr.decode()[-300:]}")
                
                # 2. Create 6-second video from CTA image
                cta_mp4 = os.path.join(temp_dir, f"{job_id}_cta.mp4")
                files_to_clean.append(cta_mp4)
                
                if has_watermark:
                    cta_cmd = [
                        "ffmpeg", "-y", "-threads", "1",
                        "-loop", "1", "-i", cta_image,
                        "-i", watermark_path,
                        "-t", str(cta_duration), 
                        "-filter_complex", "[0:v]scale=480:854:force_original_aspect_ratio=increase,crop=480:854,fps=30,format=yuv420p[bg];[1:v]scale=100:-1[wm];[bg][wm]overlay=W-w-15:15",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",
                        cta_mp4
                    ]
                else:
                    cta_cmd = [
                        "ffmpeg", "-y", "-threads", "1",
                        "-loop", "1", "-i", cta_image,
                        "-t", str(cta_duration), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",
                        "-vf", "scale=480:854:force_original_aspect_ratio=increase,crop=480:854,fps=30,format=yuv420p",
                        cta_mp4
                    ]
                logger.info(f"FFmpeg: Generating CTA clip from {os.path.basename(cta_image)}...")
                proc_cta = await asyncio.create_subprocess_exec(*cta_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr = await asyncio.wait_for(proc_cta.communicate(), timeout=60)
                if proc_cta.returncode != 0:
                    logger.error(f"FFmpeg CTA generation failed: {stderr.decode()[-300:]}")
                
                # 3. Write final concat list
                with open(final_concat_list, "w") as f:
                    f.write(f"file '{os.path.basename(main_video_mp4)}'\n")
                    f.write(f"file '{os.path.basename(cta_mp4)}'\n")
            else:
                # Fallback if no CTA images or audio too short
                with open(final_concat_list, "w") as f:
                    f.write(f"file '{os.path.basename(concat_output)}'\n")
            
            # Step 3: Merge with audio
            logger.info(f"FFmpeg: Merging final video with audio and subtitles...")
            srt_path = audio_path.replace(".wav", ".srt").replace(".mp3", ".srt")
            has_srt = await self._generate_srt(audio_path, srt_path)
            if has_srt:
                files_to_clean.append(srt_path)
                
            safe_srt_path = srt_path.replace("\\", "/") # FFmpeg filter path safety
            
            if has_srt:
                # Re-encode final video to burn subtitles
                merge_cmd = [
                    "ffmpeg", "-y", "-threads", "1",
                    "-stream_loop", "-1" if not cta_image else "0",
                    "-f", "concat", "-safe", "0",
                    "-i", final_concat_list,
                    "-i", audio_path,
                    "-vf", f"subtitles={safe_srt_path}:force_style='Fontname=Liberation Sans,Fontsize=18,PrimaryColour=&H0000FFFF,OutlineColour=&H80000000,BorderStyle=3,Outline=1,Shadow=1,MarginV=80,Alignment=2'",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
                    "-rc-lookahead", "0",
                    "-bf", "0",
                    "-tune", "fastdecode",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k",
                    "-shortest",
                    "-movflags", "+faststart",
                    output_path
                ]
            else:
                # Standard fast copy if no subtitles
                merge_cmd = [
                    "ffmpeg", "-y", "-threads", "1",
                    "-stream_loop", "-1" if not cta_image else "0",
                    "-f", "concat", "-safe", "0",
                    "-i", final_concat_list,
                    "-i", audio_path,
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "128k",
                    "-shortest",
                    "-movflags", "+faststart",
                    output_path
                ]
            
            logger.info(f"FFmpeg: Final merge starting...")
            process = await asyncio.create_subprocess_exec(
                *merge_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            
            if process.returncode != 0:
                logger.error(f"FFmpeg merge failed: {stderr.decode()[-500:]}")
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
            if 'files_to_clean' in locals():
                for f in files_to_clean:
                    if f and os.path.exists(f):
                        try:
                            os.remove(f)
                        except Exception:
                            pass
    async def _search_pexels(self, session, query, used_video_ids):
        """Search Pexels API with technical fallbacks (async)."""
        query = query.strip().lower()
        
        # Stricter technical filtering
        search_query = f"{query} construction engineering"
        
        fallbacks = [
            search_query,
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
                        import random
                        videos_list = data["videos"]
                        random.shuffle(videos_list)
                        
                        for video in videos_list:
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
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as response:
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
