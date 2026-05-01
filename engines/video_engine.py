import os
import logging
import asyncio
import aiohttp
import traceback
from core.config import settings

logger = logging.getLogger(__name__)

MAX_SCENES = 6          # Hard cap on scenes to limit memory
CLIP_DURATION = 10      # 10s per clip × 6 scenes = ~60s video (ideal for YouTube Shorts)
OUTPUT_W = 480          # Width (portrait)
OUTPUT_H = 854          # Height (portrait 9:16)
OUTPUT_FPS = 24         # Lower FPS = less memory


class VideoEngine:
    def __init__(self):
        self.pexels_api_key = settings.PEXELS_API_KEY

    async def assemble_video(self, job_id, narration_path, script_data):
        """Orchestrate the hybrid visual assembly."""
        output_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_final.mp4")
        scenes = script_data.get("scenes", [])[:MAX_SCENES]  # Cap at MAX_SCENES

        logger.info(f"Job {job_id}: Assembling {len(scenes)} scenes (max {MAX_SCENES})")

        if not scenes:
            logger.error(f"Job {job_id}: No scenes found in script_data")
            return None

        # 1. Download clips one at a time (sequential, not parallel — saves peak RAM)
        scene_clips = await self._gather_assets(job_id, scenes)
        if not scene_clips:
            logger.error(f"Job {job_id}: No clips downloaded — cannot render")
            return None

        logger.info(f"Job {job_id}: Downloaded {len(scene_clips)} clips, starting single-pass FFmpeg render")

        # 2. Single FFmpeg pass — filter_complex handles scaling + concat + audio merge
        success = await self._render_single_pass(scene_clips, narration_path, output_path, job_id)

        # Cleanup downloaded clips
        for p in scene_clips:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

        if success and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"Job {job_id}: Video ready ({file_size // 1024}KB)")
            return output_path
        else:
            logger.error(f"Job {job_id}: FFmpeg render failed")
            return None

    async def _gather_assets(self, job_id, scenes):
        """Download one clip per scene sequentially to control peak RAM."""
        clips = []
        used_ids = set()

        async with aiohttp.ClientSession() as session:
            for i, scene in enumerate(scenes):
                query = scene.get("visual_query", "civil engineering")
                logger.info(f"Job {job_id}: Scene {i+1}/{len(scenes)} — Pexels search: '{query}'")

                url = await self._search_pexels(session, query, used_ids)
                if not url:
                    logger.warning(f"Job {job_id}: Scene {i+1} — no Pexels result, skipping")
                    continue

                local_path = os.path.join(settings.TEMP_DIR, f"{job_id}_clip_{i}.mp4")
                ok = await self._download_file(session, url, local_path)
                if ok and os.path.exists(local_path):
                    size = os.path.getsize(local_path)
                    logger.info(f"Job {job_id}: Scene {i+1} downloaded ({size // 1024}KB)")
                    clips.append(local_path)
                else:
                    logger.warning(f"Job {job_id}: Scene {i+1} download failed")

        return clips

    async def _render_single_pass(self, clip_paths, audio_path, output_path, job_id):
        """
        Single FFmpeg command:
        - Trims each clip to CLIP_DURATION seconds
        - Scales + crops to OUTPUT_W x OUTPUT_H
        - Concatenates all clips
        - Merges with audio
        All in one process = minimal RAM usage.
        """
        try:
            n = len(clip_paths)

            # Build input args: -t CLIP_DURATION -i clip.mp4 for each clip
            input_args = []
            for p in clip_paths:
                input_args += ["-t", str(CLIP_DURATION), "-i", p]

            # Build filter_complex string
            # Each video input → scale+crop+fps+setsar → labelled [vN]
            # Then concat all [v0][v1]...[vN] together → [vout]
            filter_parts = []
            for i in range(n):
                filter_parts.append(
                    f"[{i}:v]scale={OUTPUT_W}:{OUTPUT_H}:force_original_aspect_ratio=increase,"
                    f"crop={OUTPUT_W}:{OUTPUT_H},fps={OUTPUT_FPS},setsar=1[v{i}]"
                )
            concat_inputs = "".join(f"[v{i}]" for i in range(n))
            filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vout]")
            filter_complex = ";".join(filter_parts)

            # Add audio as the last input
            audio_index = n

            cmd = [
                "ffmpeg", "-y",
                *input_args,
                "-stream_loop", "-1", "-i", audio_path,  # Loop audio if needed
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", f"{audio_index}:a",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-c:a", "aac", "-b:a", "96k",
                "-shortest",           # Stop when audio ends
                "-movflags", "+faststart",
                "-pix_fmt", "yuv420p",
                output_path
            ]

            logger.info(f"Job {job_id}: Running single-pass FFmpeg with {n} clips...")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # 5 min timeout is enough for 6 clips × 5s at 480p ultrafast
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

            if process.returncode != 0:
                err = stderr.decode()[-800:]
                logger.error(f"Job {job_id}: FFmpeg failed (rc={process.returncode}): {err}")
                # Accept file if it's large enough (FFmpeg sometimes exits non-zero but file is ok)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 100 * 1024:
                    logger.info(f"Job {job_id}: Output file valid despite non-zero exit — using it")
                    return True
                return False

            logger.info(f"Job {job_id}: FFmpeg completed successfully")
            return True

        except asyncio.TimeoutError:
            logger.error(f"Job {job_id}: FFmpeg timed out after 300s")
            return False
        except Exception as e:
            logger.error(f"Job {job_id}: FFmpeg exception: {e}")
            logger.error(traceback.format_exc())
            return False

    async def _search_pexels(self, session, query, used_ids):
        """Search Pexels for SD-quality portrait clips."""
        query = query.strip().lower()
        fallbacks = [query, f"construction {query}", "civil engineering construction", "building construction site"]
        headers = {"Authorization": self.pexels_api_key}

        for q in fallbacks:
            url = f"https://api.pexels.com/videos/search?query={q}&per_page=15&orientation=portrait"
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    for video in data.get("videos", []):
                        vid_id = video.get("id")
                        if vid_id in used_ids:
                            continue
                        files = video.get("video_files", [])
                        # Prefer SD (360-640px wide) — small file, low RAM during decode
                        sd_files = [f for f in files if 360 <= f.get("width", 0) <= 640]
                        chosen = sd_files[0] if sd_files else (files[0] if files else None)
                        if chosen:
                            used_ids.add(vid_id)
                            w = chosen.get("width", "?")
                            logger.info(f"Pexels: '{q}' → video {vid_id} ({w}px wide)")
                            return chosen["link"]
            except asyncio.TimeoutError:
                logger.warning(f"Pexels timeout for '{q}'")
            except Exception as e:
                logger.error(f"Pexels error for '{q}': {e}")

        return None

    async def _download_file(self, session, url, path):
        """Stream download to disk — never buffers full file in RAM."""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    logger.error(f"Download HTTP {resp.status}: {url[:80]}")
                    return False
                with open(path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)
            size = os.path.getsize(path)
            logger.info(f"Downloaded {size // 1024}KB → {os.path.basename(path)}")
            return True
        except asyncio.TimeoutError:
            logger.error(f"Download timeout: {url[:80]}")
            return False
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False
