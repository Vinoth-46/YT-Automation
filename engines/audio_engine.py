import os
import logging
import asyncio
import traceback
from core.config import settings

logger = logging.getLogger(__name__)


class AudioEngine:
    def __init__(self):
        self.primary_model = "models/gemini-3.1-flash-tts-preview"
        self.fallback_model = "models/gemini-2.5-flash-preview-tts"

    async def _generate_segment_audio(self, text, segment_path, job_id):
        """Generate audio for a single segment with fallback sequence."""
        # Primary: Gemini 3.5 TTS
        try:
            result = await asyncio.wait_for(
                self._generate_gemini_tts(text, segment_path, job_id, self.primary_model),
                timeout=45
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"Segment TTS primary failed: {e}")

        # Fallback 1: Gemini 3.1 TTS
        try:
            result = await asyncio.wait_for(
                self._generate_gemini_tts(text, segment_path, job_id, self.fallback_model),
                timeout=45
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"Segment TTS fallback failed: {e}")

        # Fallback 2: gTTS
        return await self._generate_gtts(text, segment_path, job_id)

    async def generate_narration(self, script_data, job_id, mode="publish"):
        """Generate narration using Gemini TTS with fallbacks.
        
        Attempts to generate scene-specific audios to match the script scenes
        and concatenates them to guarantee exact audio-visual timing sync.
        """
        scenes = script_data.get("scenes", [])
        output_filename = f"{job_id}_narration.wav"
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
        
        # Check if we can do segmented sync audio
        has_scene_narration = all(isinstance(s, dict) and s.get("narration_tamil") for s in scenes)
        
        if has_scene_narration and len(scenes) > 0:
            logger.info(f"Job {job_id}: Found scene-specific narration. Generating segmented synced audio...")
            try:
                # Setup temp directory for segments
                temp_audio_dir = os.path.join(settings.TEMP_DIR, f"{job_id}_audio_segments")
                os.makedirs(temp_audio_dir, exist_ok=True)
                
                segment_paths = []
                tasks = []
                
                for idx, scene in enumerate(scenes):
                    seg_text = scene["narration_tamil"].strip()
                    seg_path = os.path.join(temp_audio_dir, f"{job_id}_scene_{idx}_narration.wav")
                    segment_paths.append(seg_path)
                    tasks.append(self._generate_segment_audio(seg_text, seg_path, job_id))
                
                # Execute in parallel to save time
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Verify all succeeded
                all_ok = True
                for idx, res in enumerate(results):
                    if isinstance(res, Exception) or not res or not os.path.exists(segment_paths[idx]):
                        logger.error(f"Job {job_id}: Segment {idx+1} audio generation failed: {res}")
                        all_ok = False
                        break
                
                if all_ok:
                    # Concatenate with FFmpeg
                    logger.info(f"Job {job_id}: All segments generated successfully. Concatenating...")
                    concat_list_path = os.path.join(temp_audio_dir, "audio_concat.txt")
                    with open(concat_list_path, "w", encoding="utf-8") as f:
                        for path in segment_paths:
                            f.write(f"file '{os.path.abspath(path)}'\n")
                            
                    concat_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", output_path]
                    proc = await asyncio.create_subprocess_exec(
                        *concat_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                    
                    if proc.returncode == 0 and os.path.exists(output_path):
                        logger.info(f"Job {job_id}: Segmented synced audio successfully concatenated to {output_path}")
                        # We keep individual segments in temp directory so video_engine can read durations
                        return output_path
                    else:
                        logger.error(f"Job {job_id}: Audio concat failed: {stderr.decode()[-200:]}")
            except Exception as e:
                logger.error(f"Job {job_id}: Segmented audio pipeline failed: {e}. Falling back to single audio generation.")
                logger.error(traceback.format_exc())

        # Fallback to single file generation
        text = script_data.get("narration", "")
        if not text:
            logger.error(f"Job {job_id}: No narration text found in script_data")
            return None
            
        output_filename = f"{job_id}_narration.wav"
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)

        # Primary: Gemini 3.5 TTS
        try:
            logger.info(f"Job {job_id}: Attempting Gemini TTS (Primary: {self.primary_model})...")
            result = await asyncio.wait_for(
                self._generate_gemini_tts(text, output_path, job_id, self.primary_model),
                timeout=120
            )
            if result:
                return result
        except asyncio.TimeoutError:
            logger.error(f"Job {job_id}: Primary TTS timed out after 120s. Trying fallback Gemini model...")
        except Exception as e:
            logger.error(f"Job {job_id}: Primary TTS ({self.primary_model}) failed: {e}")
            logger.error(traceback.format_exc())

        # Fallback 1: Gemini 3.1 TTS
        try:
            logger.info(f"Job {job_id}: Attempting Gemini TTS (Fallback: {self.fallback_model})...")
            result = await asyncio.wait_for(
                self._generate_gemini_tts(text, output_path, job_id, self.fallback_model),
                timeout=120
            )
            if result:
                return result
        except asyncio.TimeoutError:
            logger.error(f"Job {job_id}: Fallback TTS timed out after 120s. Trying gTTS...")
        except Exception as e:
            logger.error(f"Job {job_id}: Fallback TTS ({self.fallback_model}) failed: {e}")
            logger.error(traceback.format_exc())

        # Fallback 2: gTTS (always works, no API quota)
        logger.info(f"Job {job_id}: Using gTTS fallback...")
        return await self._generate_gtts(text, output_path, job_id)

    async def _generate_gemini_tts(self, text, output_path, job_id, model_name):
        """Generate high-quality Tamil audio using a specific Gemini TTS model."""
        try:
            from google import genai
            from google.genai import types
            
            # Support multiple keys
            api_keys = [k.strip() for k in settings.GEMINI_API_KEY.split(",") if k.strip()]
            
            prompt = (
                "You are a professional Tamil narrator for an educational YouTube channel. "
                "Speak clearly with a warm, engaging, and confident tone. "
                "Use natural Tamil pronunciation with moderate pacing. "
                f"\n\n{text}"
            )

            response = None
            last_error = None
            
            for i, key in enumerate(api_keys):
                try:
                    client = genai.Client(api_key=key)
                    logger.info(f"Job {job_id}: Calling Gemini TTS model {model_name} (Key #{i+1})...")
                    
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_modalities=["audio"],
                            speech_config=types.SpeechConfig(
                                voice_config=types.VoiceConfig(
                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                        voice_name="Sadaltager"
                                    )
                                )
                            )
                        )
                    )
                    break # Success!
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    if "429" in error_str or "quota" in error_str:
                        logger.warning(f"Job {job_id}: Key #{i+1} hit rate limit. Trying next key...")
                        continue
                    else:
                        # Non-quota error, probably model name or network
                        raise e

            if not response:
                raise last_error or Exception("No response from any Gemini key")

            logger.info(f"Job {job_id}: Gemini TTS response received, extracting audio...")

            # Extract audio data from response
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    audio_data = part.inline_data.data
                    mime_type = part.inline_data.mime_type
                    logger.info(f"Job {job_id}: Audio data found, mime_type={mime_type}, size={len(audio_data)} bytes")

                    if "wav" in mime_type:
                        with open(output_path, "wb") as f:
                            f.write(audio_data)
                    else:
                        # Save as raw temp file and convert to WAV via ffmpeg
                        temp_path = output_path.replace(".wav", ".raw")
                        with open(temp_path, "wb") as f:
                            f.write(audio_data)

                        # For Gemini l16 audio, specify the input format
                        process = await asyncio.create_subprocess_exec(
                            "ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                            "-i", temp_path, output_path,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

                        if os.path.exists(temp_path):
                            os.remove(temp_path)

                        if process.returncode != 0:
                            logger.error(f"Job {job_id}: FFmpeg conversion failed: {stderr.decode()[-300:]}")
                            return None

                    if os.path.exists(output_path):
                        file_size = os.path.getsize(output_path)
                        logger.info(f"Job {job_id}: Gemini TTS audio saved ({file_size // 1024}KB)")
                        return output_path
                    else:
                        logger.error(f"Job {job_id}: Gemini TTS output file not found")
                        return None

            logger.error(f"Job {job_id}: No audio data in Gemini TTS response")
            return None
        except Exception as e:
            logger.error(f"Job {job_id}: Gemini TTS error: {e}")
            raise

    async def _generate_gtts(self, text, output_path, job_id):
        """Generate audio using Google Text-to-Speech (gTTS) as fallback."""
        try:
            from gtts import gTTS

            logger.info(f"Job {job_id}: Generating gTTS audio (Tamil)...")
            
            # gTTS supports Tamil natively
            tts = gTTS(text=text, lang="ta", slow=False)
            mp3_path = output_path.replace(".wav", ".mp3")

            await asyncio.to_thread(tts.save, mp3_path)
            
            if not os.path.exists(mp3_path):
                logger.error(f"Job {job_id}: gTTS failed to save MP3")
                return None
            
            mp3_size = os.path.getsize(mp3_path)
            logger.info(f"Job {job_id}: gTTS MP3 saved ({mp3_size // 1024}KB), converting to WAV...")

            # Convert MP3 to WAV using ffmpeg for compatibility
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", mp3_path,
                "-ar", "22050", "-ac", "1", output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

            if process.returncode == 0:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
                file_size = os.path.getsize(output_path)
                logger.info(f"Job {job_id}: gTTS audio ready ({file_size // 1024}KB)")
                return output_path
            else:
                logger.error(f"Job {job_id}: FFmpeg WAV conversion failed: {stderr.decode()[-300:]}")
                # Use mp3 directly if ffmpeg fails
                if os.path.exists(mp3_path):
                    os.rename(mp3_path, output_path)
                    logger.info(f"Job {job_id}: Using MP3 directly as fallback")
                    return output_path
                return None
        except Exception as e:
            logger.error(f"Job {job_id}: gTTS fallback error: {e}")
            logger.error(traceback.format_exc())
            return None
