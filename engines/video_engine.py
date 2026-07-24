import os
import logging
import asyncio
import aiohttp
import httpx
import traceback
from core.config import settings
from engines.animation_engine import AnimationEngine

logger = logging.getLogger(__name__)

class VideoEngine:
    def __init__(self):
        self.pexels_api_key = settings.PEXELS_API_KEY
        self.animation_engine = AnimationEngine()

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
        success = await self._render_ffmpeg(scene_assets, narration_path, output_path, script_data=script_data)
        
        if success and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"Job {job_id}: Video rendered successfully ({file_size // 1024}KB)")
            
            # Generate custom thumbnail
            thumbnail_text = script_data.get("metadata", {}).get("thumbnail_text", "AVOID THIS MISTAKE")
            thumbnail_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_thumbnail.jpg")
            try:
                self.generate_thumbnail(output_path, thumbnail_path, thumbnail_text)
            except Exception as te:
                logger.error(f"Job {job_id}: Failed to generate thumbnail: {te}")
                
            return output_path
        else:
            logger.error(f"Job {job_id}: FFmpeg render failed or output file not found")
            return None

    async def _gather_assets(self, job_id, scenes):
        """Fetch stock videos from Pexels/Pixabay or YouTube with full fallbacks (async)."""
        assets = []
        
        # Load persistent used video IDs to avoid repetition across runs
        # Format: "video_id|timestamp" per line for expiry tracking
        used_videos_file = os.path.join(settings.OUTPUT_DIR, "used_video_ids.txt")
        used_video_ids = set()
        import time
        now = time.time()
        max_age_seconds = 30 * 24 * 3600  # 30 days expiry
        valid_lines = []
        
        if os.path.exists(used_videos_file):
            try:
                with open(used_videos_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split("|", 1)
                        vid_id = parts[0]
                        ts = float(parts[1]) if len(parts) > 1 else 0
                        if now - ts < max_age_seconds:
                            used_video_ids.add(str(vid_id))
                            valid_lines.append(f"{vid_id}|{ts}")
                logger.info(f"Loaded {len(used_video_ids)} valid video IDs from cache (expired entries purged)")
            except Exception as e:
                logger.warning(f"Could not load used video IDs: {e}")
        
        def _persist_cache():
            """Write current used_video_ids to disk immediately."""
            try:
                with open(used_videos_file, "w") as f:
                    for entry in valid_lines:
                        f.write(f"{entry}\n")
            except Exception as e:
                logger.warning(f"Could not save used video IDs: {e}")
        
        async with aiohttp.ClientSession() as session:
            for i, scene in enumerate(scenes):
                query = scene.get("visual_query", "civil engineering")
                local_path = os.path.join(settings.TEMP_DIR, f"{job_id}_scene_{i}.mp4")
                downloaded_success = False
                
                # Try AI Video Generation if enabled
                if settings.VIDEO_SOURCE == "ai":
                    ai_prompt = scene.get("ai_video_prompt") or query
                    if ai_prompt:
                        logger.info(f"Job {job_id}: Scene {i+1}/{len(scenes)} — Generating via Wan 2.1 AI...")
                        try:
                            from engines.ai_video_engine import AIVideoEngine
                            ai_engine = AIVideoEngine()
                            ai_clip_path = await ai_engine.generate_scene_clip(ai_prompt, job_id, i)
                            if ai_clip_path and os.path.exists(ai_clip_path):
                                logger.info(f"Job {job_id}: Scene {i+1} successfully generated via AI: {ai_clip_path}")
                                assets.append(ai_clip_path)
                                continue
                            else:
                                logger.warning(f"Job {job_id}: AI generation failed for Scene {i+1}, falling back to stock search...")
                        except Exception as e:
                            logger.error(f"Job {job_id}: AI Video Engine error for Scene {i+1}: {e}. Falling back to stock...")
                
                logger.info(f"Job {job_id}: Scene {i+1}/{len(scenes)} — searching Pexels & Pixabay for '{query}'")
                
                # Check both platforms sequentially with increasing fallback generality to maximize relevance
                search_steps = [
                    # (platform, query_string, orientation)
                    ("pexels", query, "portrait"),
                    ("pixabay", query, None),
                    ("pexels", query, "all"),
                    ("pexels", f"{query} construction", "portrait"),
                    ("pixabay", f"{query} construction", None),
                    ("pexels", "civil engineering construction", "portrait"),
                    ("pixabay", "civil engineering construction", None),
                    ("pexels", "building site", "portrait"),
                    ("pixabay", "building site", None)
                ]
                
                asset_url = None
                for platform, q_str, orient in search_steps:
                    if platform == "pexels":
                        asset_url = await self._search_pexels(session, q_str, used_video_ids, valid_lines, orientation=orient)
                    else:
                        asset_url = await self._search_pixabay(session, q_str, used_video_ids, valid_lines)
                        
                    if asset_url:
                        logger.info(f"Job {job_id}: Scene {i+1} — found match on {platform} for '{q_str}'")
                        break
                    
                if asset_url:
                    downloaded_success = await self._download_file(session, asset_url, local_path)
                
                if downloaded_success and os.path.exists(local_path):
                    file_size = os.path.getsize(local_path)
                    logger.info(f"Job {job_id}: Scene {i+1} downloaded ({file_size // 1024}KB)")
                    assets.append(local_path)
                    _persist_cache()
                else:
                    logger.warning(f"Job {job_id}: Scene {i+1} download failed")
        
        return assets
        
    async def _generate_srt(self, audio_path, srt_path, script_data=None):
        """Generate English subtitles/translations using Groq Whisper API (primary) with Gemini fallback.
        
        Using Groq Whisper Translation translates Tamil audio narration natively to English.
        """
        # --- Method 1: Groq Whisper API (Highly accurate translation) ---
        groq_api_key = settings.GROQ_API_KEY
        if groq_api_key:
            try:
                logger.info("Attempting translation with Groq Whisper API...")
                url = "https://api.groq.com/openai/v1/audio/translations"
                headers = {"Authorization": f"Bearer {groq_api_key}"}
                
                with open(audio_path, "rb") as f:
                    files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
                    data = {
                        "model": "whisper-large-v3",
                        "response_format": "verbose_json"
                    }
                    
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(url, headers=headers, files=files, data=data, timeout=60.0)
                
                if resp.status_code == 200:
                    result = resp.json()
                    words = result.get("words", [])
                    if not words and "segments" in result:
                        words = []
                        for seg in result["segments"]:
                            if "words" in seg:
                                words.extend(seg["words"])
                    
                    if words:
                        # Group words into 1-2 word clauses (max duration 1.0 second, gap 0.3s)
                        chunks = []
                        current_chunk = []
                        max_words = 2
                        max_gap = 0.3
                        max_duration = 1.0
                        
                        for w_data in words:
                            word = w_data.get("word", "")
                            start = w_data.get("start")
                            end = w_data.get("end")
                            
                            if start is None or end is None:
                                continue
                                
                            word_clean = word.strip()
                            if not word_clean:
                                continue
                                
                            if current_chunk:
                                last_word = current_chunk[-1]
                                gap = start - last_word.get("end", start)
                                duration = end - current_chunk[0].get("start", start)
                                last_word_clean = last_word.get("word", "").strip()
                                has_punctuation = any(char in last_word_clean for char in [".", ",", "!", "?", "।"])
                                
                                if gap > max_gap or duration > max_duration or len(current_chunk) >= max_words or has_punctuation:
                                    chunks.append(current_chunk)
                                    current_chunk = []
                                    
                            current_chunk.append(w_data)
                            
                        if current_chunk:
                            chunks.append(current_chunk)
                            
                        # Format SRT
                        def format_time(seconds):
                            ms = int((seconds % 1) * 1000)
                            m, s = divmod(int(seconds), 60)
                            h, m = divmod(m, 60)
                            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                            
                        with open(srt_path, "w", encoding="utf-8") as f:
                            for idx, chunk in enumerate(chunks):
                                start_str = format_time(chunk[0]["start"])
                                end_str = format_time(chunk[-1]["end"])
                                text_str = " ".join(w["word"].strip() for w in chunk)
                                f.write(f"{idx+1}\n{start_str} --> {end_str}\n{text_str}\n\n")
                                
                        logger.info(f"Groq transcription/translation complete. SRT with {len(chunks)} synchronized chunks saved to {srt_path}")
                        return True
                    elif "segments" in result:
                        # Fallback to segment-level translation output (normal for translation endpoint)
                        chunks = []
                        for seg in result["segments"]:
                            start = seg.get("start")
                            end = seg.get("end")
                            text = seg.get("text", "").strip()
                            if start is not None and end is not None and text:
                                chunks.append({
                                    "start": start,
                                    "end": end,
                                    "text": text
                                })
                                
                        def format_time(seconds):
                            ms = int((seconds % 1) * 1000)
                            m, s = divmod(int(seconds), 60)
                            h, m = divmod(m, 60)
                            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                            
                        with open(srt_path, "w", encoding="utf-8") as f:
                            for idx, chunk in enumerate(chunks):
                                start_str = format_time(chunk["start"])
                                end_str = format_time(chunk["end"])
                                f.write(f"{idx+1}\n{start_str} --> {end_str}\n{chunk['text']}\n\n")
                                
                        logger.info(f"Groq translation complete. SRT with {len(chunks)} translated segments saved to {srt_path}")
                        return True
                    else:
                        logger.warning("Groq Whisper Translation API returned no translation in response.")
                else:
                    logger.warning(f"Groq Whisper Translation API error (status {resp.status_code}): {resp.text}")
            except Exception as e:
                logger.error(f"Groq Whisper Translation API call failed: {e}")
                logger.error(traceback.format_exc())
                
        # --- Method 2: Gemini 2.5 Flash (Fallback translation) ---
        try:
            logger.info("Falling back to cloud translation with Gemini 2.5 Flash...")
            
            from google import genai
            from google.genai import types
            import time
            
            api_keys = [k.strip() for k in settings.GEMINI_API_KEY.split(",") if k.strip()]
            
            prompt = (
                "Listen to this Tamil audio narration, translate it into English, and provide a precise English translation in SRT (SubRip) format. "
                "Each caption should be 3-5 words long for fast-paced YouTube Shorts. "
                "Ensure timestamps are exact (format: HH:MM:SS,mmm). "
                "Only return the SRT content, no extra text."
            )

            audio_file = None
            client = None
            last_error = None
            
            for i, key in enumerate(api_keys):
                try:
                    client = genai.Client(api_key=key)
                    
                    logger.info(f"Uploading audio for translation (Key #{i+1}): {os.path.basename(audio_path)}")
                    with open(audio_path, 'rb') as f:
                        audio_file = client.files.upload(file=f, config={'mime_type': 'audio/wav'})
                    
                    # Wait for processing
                    while audio_file.state.name == "PROCESSING":
                        time.sleep(2)
                        audio_file = client.files.get(name=audio_file.name)
                    
                    if audio_file.state.name == "FAILED":
                        logger.warning(f"Gemini audio processing failed with Key #{i+1}. Trying next key...")
                        continue

                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[audio_file, prompt],
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            top_p=0.95,
                            top_k=40,
                        )
                    )
                    
                    srt_content = response.text.strip()
                    
                    if srt_content.startswith("```"):
                        lines = srt_content.split("\n")
                        if len(lines) > 2:
                            srt_content = "\n".join(lines[1:-1])
                        else:
                            srt_content = srt_content.replace("```srt", "").replace("```", "").strip()

                    if not srt_content or "1" not in srt_content:
                        logger.warning(f"Gemini returned invalid SRT with Key #{i+1}. Trying next key...")
                        continue

                    with open(srt_path, "w", encoding="utf-8") as f:
                        f.write(srt_content)
                        
                    logger.info(f"Cloud translation complete. SRT saved to {srt_path}")
                    
                    try:
                        client.files.delete(name=audio_file.name)
                    except:
                        pass
                        
                    return True

                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    if "429" in error_str or "quota" in error_str or "key not valid" in error_str:
                        logger.warning(f"Gemini Key #{i+1} failed ({error_str[:100]}). Rotating...")
                        continue
                    else:
                        logger.error(f"Gemini Key #{i+1} unexpected error: {e}")
                        continue

            if last_error:
                raise last_error
            return False

        except Exception as e:
            logger.error(f"Gemini fallback transcription failed: {e}")
            logger.error(traceback.format_exc())
            return False

    def _get_audio_duration(self, path):
        """Retrieve exact duration of an audio file using ffprobe."""
        try:
            import subprocess
            res = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, check=True
            )
            return float(res.stdout.strip())
        except Exception as e:
            logger.warning(f"Failed to get audio duration for {path}: {e}")
            return None

    async def _render_ffmpeg(self, scene_paths, audio_path, output_path, script_data=None):
        """Standardize clips, concatenate, and sync with audio using FFmpeg.
        
        Kaggle-optimized: 1080x1920, CRF 23, 2 threads, Tamil font subtitles.
        """
        job_id = os.path.basename(audio_path).split('_')[0]
        temp_dir = os.path.dirname(audio_path) or settings.TEMP_DIR
        
        # === Kaggle Quality Settings (31GB RAM available) ===
        VID_W, VID_H = 1080, 1920
        CRF = "23"
        PRESET = "medium"
        THREADS = "2"
        WM_SCALE = 150
        
        processed_clips = []
        concat_file = None
        concat_output = None
        
        try:
            dirs_to_clean = []
            temp_audio_dir = os.path.join(settings.TEMP_DIR, f"{job_id}_audio_segments")
            if os.path.exists(temp_audio_dir):
                dirs_to_clean.append(temp_audio_dir)
            # Step 0: Ensure Tamil Font exists
            fonts_dir = os.path.join(os.getcwd(), "assets", "fonts")
            os.makedirs(fonts_dir, exist_ok=True)
            tamil_font_path = os.path.join(fonts_dir, "NotoSansTamil-Bold.ttf")
            latin_font_path = os.path.join(fonts_dir, "NotoSans-Bold.ttf")

            if not os.path.exists(tamil_font_path):
                logger.info("Downloading Noto Sans Tamil font...")
                import urllib.request
                tamil_font_urls = [
                    "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTamil/NotoSansTamil-Bold.ttf",
                    "https://github.com/google/fonts/raw/main/ofl/notosanstamil/NotoSansTamil%5Bwdth%2Cwght%5D.ttf",
                    "https://cdn.jsdelivr.net/gh/googlefonts/noto-fonts@main/hinted/ttf/NotoSansTamil/NotoSansTamil-Bold.ttf",
                ]
                for url in tamil_font_urls:
                    try:
                        urllib.request.urlretrieve(url, tamil_font_path)
                        if os.path.exists(tamil_font_path) and os.path.getsize(tamil_font_path) > 1000:
                            logger.info(f"Tamil font downloaded from {url.split('/')[2]}")
                            break
                    except Exception as fe:
                        logger.warning(f"Font download failed from {url.split('/')[2]}: {fe}")
                        continue

            # Also download Noto Sans Bold for Latin/English characters
            # (NotoSansTamil has no Latin glyphs — English words show as □ without this)
            if not os.path.exists(latin_font_path):
                logger.info("Downloading Noto Sans (Latin fallback) font...")
                import urllib.request
                latin_font_urls = [
                    "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf",
                    "https://cdn.jsdelivr.net/gh/googlefonts/noto-fonts@main/hinted/ttf/NotoSans/NotoSans-Bold.ttf",
                ]
                for url in latin_font_urls:
                    try:
                        urllib.request.urlretrieve(url, latin_font_path)
                        if os.path.exists(latin_font_path) and os.path.getsize(latin_font_path) > 1000:
                            logger.info(f"Latin font downloaded from {url.split('/')[2]}")
                            break
                    except Exception as le:
                        logger.warning(f"Latin font download failed from {url.split('/')[2]}: {le}")
                        continue

            # Build a custom fonts.conf so FFmpeg/libass finds the Tamil font
            # without relying on the system fontconfig cache (which is unreliable on Kaggle)
            try:
                import subprocess
                import shutil
                fc_cache_dir = os.path.join(fonts_dir, "fc_cache")
                os.makedirs(fc_cache_dir, exist_ok=True)
                fonts_conf_path = os.path.join(fonts_dir, "fonts.conf")
                fonts_conf_content = (
                    '<?xml version="1.0"?>\n'
                    '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
                    '<fontconfig>\n'
                    f'  <dir>{os.path.abspath(fonts_dir)}</dir>\n'
                    f'  <cachedir>{os.path.abspath(fc_cache_dir)}</cachedir>\n'
                    '  <match target="font">\n'
                    '    <edit name="antialias" mode="assign"><bool>true</bool></edit>\n'
                    '  </match>\n'
                    '</fontconfig>\n'
                )
                with open(fonts_conf_path, 'w') as fconf:
                    fconf.write(fonts_conf_content)
                # Build fontconfig cache using our custom config
                fc_env = os.environ.copy()
                fc_env["FONTCONFIG_FILE"] = fonts_conf_path
                result = subprocess.run(
                    ["fc-cache", "-fv"], env=fc_env, check=False,
                    capture_output=True, text=True
                )
                logger.info(f"Font cache ready. fc-cache: {result.stdout[-100:].strip()}")
            except Exception as fe:
                logger.warning(f"Font cache setup failed (non-fatal): {fe}")
                fonts_conf_path = None
            
            logger.info(f"FFmpeg: Pre-processing {len(scene_paths)} clips to {VID_W}x{VID_H} HD (max 9s per clip)...")
            
            # Step 1: Pre-process each clip individually
            watermark_path = os.path.join(os.getcwd(), "assets", "Watermark", "loading-logo.webp")
            has_watermark = getattr(settings, "ENABLE_WATERMARK", False) and os.path.exists(watermark_path)
            logger.info(f"Job {job_id}: Watermark enabled: {has_watermark} (path: {watermark_path})")
            
            scenes = script_data.get("scenes", []) if script_data else []
            
            import random as _rand
            
            for idx, p in enumerate(scene_paths):
                processed_path = p.replace(".mp4", f"_std_{idx}.mp4")
                
                # Determine exact clip duration from synced segment audio
                seg_audio_path = os.path.join(temp_audio_dir, f"{job_id}_scene_{idx}_narration.wav")
                seg_duration = None
                if os.path.exists(seg_audio_path):
                    seg_duration = self._get_audio_duration(seg_audio_path)
                
                if seg_duration is not None and seg_duration > 0.0:
                    clip_duration = seg_duration
                    logger.info(f"Scene {idx+1}: Synced to segment audio duration: {clip_duration:.2f}s")
                else:
                    clip_duration = _rand.uniform(8.0, 10.0)
                    logger.info(f"Scene {idx+1}: Fallback to random duration: {clip_duration:.2f}s")

                # Dynamic visual text overlay for high user retention
                # Text overlays are completely disabled per user request
                text_overlay = ""
                
                if text_overlay:
                    import re as _re
                    contains_tamil = bool(_re.search(r'[\u0B80-\u0BFF]', text_overlay))
                    text_esc = text_overlay.upper().replace("'", "'\\\\''").replace(":", "\\:")
                    
                    # Always use absolute, escaped paths for fontfile to completely bypass Fontconfig crashes on Windows
                    f_path = tamil_font_path if contains_tamil else latin_font_path
                    font_abs = os.path.abspath(f_path).replace("\\", "/")
                    font_abs_esc = font_abs.replace(":", "\\:")
                    
                    font_arg = f"fontfile='{font_abs_esc}'"
                    logger.info(f"Adding text overlay to scene {idx+1}: '{text_overlay}' (font: '{font_abs_esc}')")
                        
                    drawtext_str = f",drawtext={font_arg}:text='{text_esc}':fontcolor=yellow:fontsize=80:borderw=6:bordercolor=black:x=(w-text_w)/2:y=380"
                else:
                    drawtext_str = ""

                # Scale and crop landscape videos to 1080x1920 portrait aspect ratio
                scale_crop = f"scale={VID_W}:{VID_H}:force_original_aspect_ratio=increase,crop={VID_W}:{VID_H},format=yuv420p{drawtext_str}"

                # ── Animation Generation ──────────────────────────────────────
                anim_input_args = []
                anim_temp_dir = ""
                
                scene_config = scenes[idx] if idx < len(scenes) else {}
                anim_config = scene_config.get("animation") if getattr(settings, "ENABLE_ANIMATION_OVERLAY", False) else None
                
                if anim_config and isinstance(anim_config, dict) and anim_config.get("type"):
                    anim_temp_dir = os.path.join(temp_dir, f"{job_id}_scene_{idx}_anim")
                    try:
                        pattern_path = self.animation_engine.render_animation(
                            anim_config, 
                            duration=clip_duration, 
                            output_dir=anim_temp_dir
                        )
                        pattern_rel = os.path.relpath(pattern_path).replace(chr(92), '/')
                        anim_input_args = ["-framerate", "30", "-i", pattern_rel]
                        dirs_to_clean.append(anim_temp_dir)
                        logger.info(f"Scene {idx+1}: Generated animation overlay of type '{anim_config.get('type')}'")
                    except Exception as ae:
                        logger.error(f"Scene {idx+1}: Failed to generate animation: {ae}")
                        anim_input_args = []
                        anim_temp_dir = ""
                else:
                    logger.info(f"Scene {idx+1}: No animation config (anim_config={anim_config})")

                # Query input video duration to see if we need to loop it
                p_duration = self._get_audio_duration(p)
                loop_input = p_duration is None or p_duration < clip_duration
                
                # Build dynamic FFmpeg command
                cmd = ["ffmpeg", "-y"]
                if loop_input:
                    logger.info(f"Scene {idx+1}: Video duration ({f'{p_duration:.2f}' if p_duration else 'unknown'}s) is shorter than scene duration ({clip_duration:.2f}s). Looping input...")
                    cmd += ["-stream_loop", "-1"]
                cmd += ["-i", p]
                next_input_idx = 1
                
                watermark_input_idx = -1
                if has_watermark:
                    cmd += ["-i", watermark_path]
                    watermark_input_idx = next_input_idx
                    next_input_idx += 1
                    
                anim_input_idx = -1
                if anim_input_args:
                    cmd += anim_input_args
                    anim_input_idx = next_input_idx
                    next_input_idx += 1
                    
                # Build filter complex
                filter_parts = [f"[0:v]{scale_crop}[bg]"]
                last_label = "[bg]"
                
                if anim_input_idx != -1:
                    filter_parts.append(f"[{anim_input_idx}:v]scale={VID_W}:{VID_H}[anim]")
                    filter_parts.append(f"{last_label}[anim]overlay=0:0[bg_anim]")
                    last_label = "[bg_anim]"
                    
                if watermark_input_idx != -1:
                    filter_parts.append(f"[{watermark_input_idx}:v]scale={WM_SCALE}:-1[wm]")
                    filter_parts.append(f"{last_label}[wm]overlay=W-w-15:15[out_v]")
                    last_label = "[out_v]"
                    
                filter_complex_str = ";".join(filter_parts)

                cmd += [
                    "-t", str(clip_duration),
                    "-threads", THREADS
                ]
                
                if watermark_input_idx == -1 and anim_input_idx == -1:
                    cmd += ["-vf", scale_crop]
                else:
                    cmd += [
                        "-filter_complex", filter_complex_str,
                        "-map", last_label
                    ]
                    
                cmd += [
                    "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
                    "-max_muxing_queue_size", "2048",
                    "-an",
                    processed_path
                ]

                logger.info(f"Scene {idx+1}: trimmed to {clip_duration:.1f}s (animation: {anim_input_idx != -1})")
                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=600)
                
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
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-r", "30", "-an",
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
                    "ffmpeg", "-y", "-threads", THREADS,
                    "-stream_loop", "-1", "-i", concat_output,
                    "-t", str(main_duration),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-r", "30",
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
                        "ffmpeg", "-y", "-threads", THREADS,
                        "-loop", "1", "-i", cta_image,
                        "-i", watermark_path,
                        "-t", str(cta_duration), 
                        "-filter_complex", f"[0:v]scale={VID_W}:{VID_H}:force_original_aspect_ratio=increase,crop={VID_W}:{VID_H},fps=30,format=yuv420p[bg];[1:v]scale={WM_SCALE}:-1[wm];[bg][wm]overlay=W-w-15:15",
                        "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
                        cta_mp4
                    ]
                else:
                    cta_cmd = [
                        "ffmpeg", "-y", "-threads", THREADS,
                        "-loop", "1", "-i", cta_image,
                        "-t", str(cta_duration), "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
                        "-vf", f"scale={VID_W}:{VID_H}:force_original_aspect_ratio=increase,crop={VID_W}:{VID_H},fps=30,format=yuv420p",
                        cta_mp4
                    ]
                logger.info(f"FFmpeg: Generating CTA clip from {os.path.basename(cta_image)}...")
                proc_cta = await asyncio.create_subprocess_exec(*cta_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr = await asyncio.wait_for(proc_cta.communicate(), timeout=60)
                if proc_cta.returncode != 0:
                    logger.error(f"FFmpeg CTA generation failed: {stderr.decode()[-300:]}")
                
                # 3. Final concat list - use absolute paths to avoid CWD issues
                with open(final_concat_list, "w") as f:
                    f.write(f"file '{os.path.abspath(main_video_mp4)}'\n")
                    f.write(f"file '{os.path.abspath(cta_mp4)}'\n")
            else:
                # Fallback if no CTA images or audio too short
                with open(final_concat_list, "w") as f:
                    f.write(f"file '{os.path.abspath(concat_output)}'\n")
            
            # Step 3: Merge with audio
            logger.info(f"FFmpeg: Merging final video with audio and subtitles...")
            srt_path = audio_path.replace(".wav", ".srt").replace(".mp3", ".srt")
            has_srt = await self._generate_srt(audio_path, srt_path, script_data=script_data)
            if has_srt:
                # Save a copy to outputs so it's ready for Closed Caption (CC) upload
                final_srt_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_final.srt")
                try:
                    import shutil
                    shutil.copy(srt_path, final_srt_path)
                    logger.info(f"Persisted SRT file to outputs: {final_srt_path}")
                except Exception as se:
                    logger.error(f"Failed to copy SRT to outputs: {se}")
                files_to_clean.append(srt_path)
                
            # Convert SRT → ASS with explicit Tamil font style baked in
            # This bypasses fontconfig name-matching entirely
            ass_path = srt_path.replace(".srt", ".ass")
            font_abs = os.path.abspath(tamil_font_path).replace("\\", "/")
            srt_abs  = os.path.abspath(srt_path)

            if has_srt and settings.SUBTITLE_MODE == "baked":
                files_to_clean.append(ass_path)
                # Build ASS from SRT using Python (no external tool needed)
                try:
                    import re as _re
                    with open(srt_abs, "r", encoding="utf-8") as sf:
                        srt_raw = sf.read()

                    def srt_time_to_ass(t):
                        """Convert SRT timestamp HH:MM:SS,mmm → ASS H:MM:SS.cc"""
                        t = t.replace(",", ".")
                        if "." not in t:
                            t += ".000"
                        parts = t.split(":")
                        if len(parts) == 2:
                            h, m, rest = "0", parts[0], parts[1]
                        elif len(parts) >= 3:
                            h, m, rest = parts[0], parts[1], parts[2]
                        else:
                            h, m, rest = "0", "0", parts[0]
                        
                        s, ms = rest.split(".")
                        cs = int(ms.ljust(3, '0')[:3]) // 10
                        return f"{int(h)}:{m}:{s}.{cs:02d}"

                    blocks = _re.split(r"\n{2,}", srt_raw.strip())
                    ass_events = []
                    for block in blocks:
                        lines = block.strip().splitlines()
                        if len(lines) < 3:
                            continue
                        times = lines[1].split(" --> ")
                        if len(times) != 2:
                            continue
                        t_start = srt_time_to_ass(times[0].strip())
                        t_end   = srt_time_to_ass(times[1].strip())
                        text = " ".join(lines[2:]).replace("\n", "\\N")
                        ass_events.append((t_start, t_end, text))

                    # ASS header: OS-aware font configuration
                    import platform
                    is_windows = platform.system() == "Windows"
                    tamil_font_name = "Nirmala UI" if is_windows else "Noto Sans Tamil"
                    latin_font_name = "Arial" if is_windows else "Noto Sans"
                    
                    ass_header = (
                        "[Script Info]\n"
                        "ScriptType: v4.00+\n"
                        "PlayResX: 1080\n"
                        "PlayResY: 1920\n"
                        "ScaledBorderAndShadow: yes\n\n"
                        "[V4+ Styles]\n"
                        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
                        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
                        "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
                        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
                        # Alignment=2 = bottom-center, MarginV=380 = 380px from bottom edge
                        f"Style: Default,{tamil_font_name},62,&H00FFFFFF,&H00FFFFFF,"
                        f"&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,60,60,380,1\n\n"
                        "[Events]\n"
                        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
                    )

                    def _add_latin_font(text):
                        """Wrap Latin/English characters with ASS inline font override.
                        NotoSansTamil has NO Latin glyphs — they render as □ boxes.
                        This switches to Noto Sans/Arial for English words, then back to Tamil.
                        """
                        import re as _re2
                        result = _re2.sub(
                            r'[A-Za-z0-9][A-Za-z0-9\'\-\.\s]*[A-Za-z0-9]|[A-Za-z0-9]',
                            lambda m: f"{{\\fn{latin_font_name}}}{m.group()}{{\\fn{tamil_font_name}}}",
                            text
                        )
                        return result
                    with open(ass_path, "w", encoding="utf-8") as af:
                        af.write(ass_header)
                        # Apply Latin font override ONLY to the text, then format event
                        final_events = []
                        for t_start, t_end, text in ass_events:
                            tagged_text = _add_latin_font(text)
                            final_events.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{tagged_text}")
                        af.write("\n".join(final_events))
                    logger.info(f"SRT converted to ASS: {ass_path} ({len(ass_events)} lines)")
                    use_ass = True
                except Exception as ae:
                    logger.warning(f"ASS conversion failed, falling back to SRT: {ae}")
                    use_ass = False

                # Set FONTCONFIG_FILE so libass finds our Tamil font
                env = os.environ.copy()
                if fonts_conf_path and os.path.exists(fonts_conf_path):
                    env["FONTCONFIG_FILE"] = fonts_conf_path
                env["FONTCONFIG_PATH"] = os.path.abspath(fonts_dir)

                # Build subtitle filter - prefer ASS (explicit style), fallback to SRT
                if use_ass:
                    # Use relative paths to avoid Windows absolute path colon splitting issue in FFmpeg
                    ass_rel = os.path.relpath(ass_path).replace(chr(92), '/')
                    fonts_rel = os.path.relpath(fonts_dir).replace(chr(92), '/')
                    ass_rel_esc = ass_rel.replace("'", "'\\\\''")
                    fonts_rel_esc = fonts_rel.replace("'", "'\\\\''")
                    sub_filter = f"ass='{ass_rel_esc}':fontsdir='{fonts_rel_esc}'"
                else:
                    srt_rel = os.path.relpath(srt_path).replace(chr(92), '/')
                    fonts_rel = os.path.relpath(fonts_dir).replace(chr(92), '/')
                    srt_rel_esc = srt_rel.replace("'", "'\\\\''")
                    fonts_rel_esc = fonts_rel.replace("'", "'\\\\''")
                    sub_filter = (
                        f"subtitles='{srt_rel_esc}'"
                        f":fontsdir='{fonts_rel_esc}'"
                        f":force_style='Fontname={tamil_font_name},Fontsize=9,"
                        f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                        f"BorderStyle=1,Outline=0.5,Shadow=0.5,"
                        f"MarginV=57,MarginL=10,MarginR=10,Alignment=2,Bold=1'"
                    )

                merge_cmd = [
                    "ffmpeg", "-y", "-threads", THREADS,
                    "-f", "concat", "-safe", "0",
                    "-i", final_concat_list,
                    "-i", audio_path,
                    "-vf", sub_filter,
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
                    "-profile:v", "high", "-level", "4.1",
                    "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                    "-shortest",
                    "-movflags", "+faststart",
                    output_path
                ]

                logger.info(f"FFmpeg: Final merge with subtitles ({('ASS' if use_ass else 'SRT')})...")
                process = await asyncio.create_subprocess_exec(
                    *merge_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )
                stdout, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=900)
                stderr_text = stderr_bytes.decode(errors='replace')

                # Log font/subtitle lines from FFmpeg stderr for diagnosis
                for line in stderr_text.splitlines():
                    ll = line.lower()
                    if any(k in ll for k in ["font", "subtitle", "ass", "libass", "cannot", "error", "warn"]):
                        logger.info(f"[FFmpeg-sub] {line.strip()}")

                if process.returncode != 0:
                    logger.error(f"FFmpeg final merge failed (code {process.returncode}): {stderr_text[-400:]}")
                    raise Exception(f"Video rendering failed: {stderr_text[-200:]}")
            else:
                # Standard re-encode if no subtitles - run it here directly
                merge_cmd = [
                    "ffmpeg", "-y", "-threads", THREADS,
                    "-f", "concat", "-safe", "0",
                    "-i", final_concat_list,
                    "-i", audio_path,
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
                    "-profile:v", "high", "-level", "4.1",
                    "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                    "-shortest",
                    "-movflags", "+faststart",
                    output_path
                ]
                logger.info(f"FFmpeg: Final merge starting (no subtitles)...")
                process = await asyncio.create_subprocess_exec(
                    *merge_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=600)
                if process.returncode != 0:
                    logger.error(f"FFmpeg no-srt merge failed: {stderr.decode()[-500:]}")
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
            if 'dirs_to_clean' in locals():
                import shutil
                for d in dirs_to_clean:
                    if d and os.path.exists(d):
                        try:
                            shutil.rmtree(d)
                        except Exception:
                            pass
    async def _search_pexels(self, session, query, used_video_ids, valid_lines, orientation="portrait"):
        """Search Pexels API for a single query (async)."""
        query = query.strip().lower()
        headers = {"Authorization": self.pexels_api_key}
        url = f"https://api.pexels.com/videos/search?query={query}&per_page=30"
        if orientation == "portrait":
            url += "&orientation=portrait"
        
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                videos = data.get("videos", [])
                if videos:
                    import random
                    random.shuffle(videos)
                    for video in videos:
                        vid_id = str(video.get("id", ""))
                        if vid_id not in used_video_ids:
                            used_video_ids.add(vid_id)
                            import time as _time
                            valid_lines.append(f"{vid_id}|{_time.time()}")
                            video_files = video.get("video_files", [])
                            for vf in video_files:
                                width = vf.get("width", 0)
                                height = vf.get("height", 0)
                                if 720 <= width <= 1920 or 720 <= height <= 1920:
                                    return vf["link"]
                            if video_files:
                                smallest = min(video_files, key=lambda x: x.get("width", 9999))
                                return smallest["link"]
        except Exception as e:
            logger.warning(f"Pexels search error for '{query}' ({orientation}): {e}")
        return None

    async def _search_pixabay(self, session, query, used_video_ids, valid_lines):
        """Search Pixabay API for a single query (async)."""
        api_key = getattr(settings, "PIXABAY_API_KEY", "")
        if not api_key:
            return None
            
        query = query.strip().lower()
        url = f"https://pixabay.com/api/videos/?key={api_key}&q={query}&per_page=30"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                hits = data.get("hits", [])
                if hits:
                    import random
                    random.shuffle(hits)
                    # Attempt 1: Portrait first
                    for hit in hits:
                        vid_id = str(hit.get("id", ""))
                        if vid_id not in used_video_ids:
                            videos = hit.get("videos", {})
                            size_key = "medium" if "medium" in videos else ("small" if "small" in videos else "large")
                            if size_key in videos:
                                vid_info = videos[size_key]
                                width = vid_info.get("width", 0)
                                height = vid_info.get("height", 0)
                                if height > width:
                                    used_video_ids.add(vid_id)
                                    import time as _time
                                    valid_lines.append(f"{vid_id}|{_time.time()}")
                                    return vid_info["url"]
                                    
                    # Attempt 2: Landscape/Any (FFmpeg will crop)
                    for hit in hits:
                        vid_id = str(hit.get("id", ""))
                        if vid_id not in used_video_ids:
                            videos = hit.get("videos", {})
                            size_key = "medium" if "medium" in videos else ("small" if "small" in videos else "large")
                            if size_key in videos:
                                vid_info = videos[size_key]
                                used_video_ids.add(vid_id)
                                import time as _time
                                valid_lines.append(f"{vid_id}|{_time.time()}")
                                return vid_info["url"]
        except Exception as e:
            logger.warning(f"Pixabay search error for '{query}': {e}")
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

    def generate_thumbnail(self, video_path, thumbnail_path, text):
        """Generate a clickbaity thumbnail from the first second of the video with styled text."""
        import subprocess
        from PIL import Image, ImageDraw, ImageFont
        
        logger.info(f"Generating thumbnail for {video_path} with text: '{text}'")
        try:
            # 1. Extract frame at 1.0 second using FFmpeg
            cmd = [
                'ffmpeg', '-y', 
                '-ss', '3.0', 
                '-i', video_path, 
                '-vframes', '1', 
                thumbnail_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if not os.path.exists(thumbnail_path):
                logger.error("FFmpeg failed to extract thumbnail frame.")
                return False
                
            # 2. Open the image with Pillow
            img = Image.open(thumbnail_path)
            draw = ImageDraw.Draw(img)
            width, height = img.size
            
            # 3. Load font (downloading if missing)
            font_dir = os.path.join(settings.BASE_DIR, "assets", "fonts")
            os.makedirs(font_dir, exist_ok=True)
            
            import re as _re
            import platform
            is_windows = platform.system() == "Windows"
            contains_tamil = bool(_re.search(r'[\u0B80-\u0BFF]', text))
            
            font_file_name = "NotoSansTamil-Bold.ttf" if contains_tamil else "NotoSans-Bold.ttf"
            font_path = os.path.join(font_dir, font_file_name)
            
            # Ensure the specific font is downloaded for non-Windows or fallback
            if not os.path.exists(font_path):
                try:
                    import httpx
                    logger.info(f"Downloading {font_file_name} for thumbnails...")
                    if contains_tamil:
                        font_url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTamil/NotoSansTamil-Bold.ttf"
                    else:
                        font_url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf"
                    resp = httpx.get(font_url)
                    if resp.status_code == 200:
                        with open(font_path, "wb") as f:
                            f.write(resp.content)
                except Exception as fe:
                    logger.warning(f"Failed to download font: {fe}")
            
            # Load the optimal font based on OS and language
            font = None
            font_loaded = False
            
            if is_windows:
                # Try system fonts first on Windows
                win_font_file = "nirmala.ttf" if contains_tamil else "arialbd.ttf"
                try:
                    font = ImageFont.truetype(win_font_file, size=120)
                    font_loaded = True
                    logger.info(f"Loaded Windows system font: {win_font_file}")
                except Exception:
                    pass
            
            if not font_loaded:
                # Try downloaded font path
                try:
                    font = ImageFont.truetype(font_path, size=120)
                    font_loaded = True
                    logger.info(f"Loaded downloaded font: {font_file_name}")
                except Exception:
                    pass
                    
            if not font_loaded:
                # Fallback to standard system fonts
                for fn in ["nirmala.ttf", "latha.ttf", "arialbd.ttf", "arial.ttf", "cour.ttf"]:
                    try:
                        font = ImageFont.truetype(fn, size=120)
                        font_loaded = True
                        logger.info(f"Loaded fallback system font: {fn}")
                        break
                    except Exception:
                        continue
                        
            if not font_loaded:
                font = ImageFont.load_default()
                logger.info("Loaded default fallback font")
                
            # 4. Text wrap & formatting
            # Let's split text into lines to fit screen width
            words = text.upper().split()
            lines = []
            current_line = []
            for word in words:
                current_line.append(word)
                line_str = " ".join(current_line)
                bbox = draw.textbbox((0, 0), line_str, font=font)
                line_width = bbox[2] - bbox[0]
                if line_width > width * 0.85:
                    if len(current_line) > 1:
                        current_line.pop()
                        lines.append(" ".join(current_line))
                        current_line = [word]
                    else:
                        lines.append(" ".join(current_line))
                        current_line = []
            if current_line:
                lines.append(" ".join(current_line))
                
            # Calculate total text block height
            line_heights = []
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_heights.append(bbox[3] - bbox[1])
                
            total_text_height = sum(line_heights) + (len(lines) - 1) * 20
            y_start = (height - total_text_height) // 2  # Center vertically
            
            # Draw dark semi-transparent backing banner
            banner_padding = 40
            banner_top = y_start - banner_padding
            banner_bottom = y_start + total_text_height + banner_padding
            
            # Create overlay image for transparency
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle(
                [(0, banner_top), (width, banner_bottom)], 
                fill=(0, 0, 0, 180) # 70% opacity black
            )
            
            # Merge back together
            img = Image.alpha_composite(img.convert('RGBA'), overlay)
            draw = ImageDraw.Draw(img)
            
            # 5. Draw text
            current_y = y_start
            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                x = (width - w) // 2
                
                # Draw text shadow
                draw.text((x+4, current_y+4), line, font=font, fill=(0, 0, 0, 255))
                # Draw text front (vibrant yellow for alternating or white)
                text_color = (255, 223, 0, 255) if (i == 0 or i == len(lines)-1) else (255, 255, 255, 255)
                draw.text((x, current_y), line, font=font, fill=text_color)
                
                current_y += h + 20
                
            # Save final JPEG
            img.convert('RGB').save(thumbnail_path, 'JPEG', quality=95)
            logger.info(f"Custom thumbnail generated successfully at {thumbnail_path}")
            return True
        except Exception as e:
            logger.error(f"Thumbnail generation failed: {e}")
            return False
