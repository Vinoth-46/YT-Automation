import os
import logging
import asyncio
import traceback
from core.config import settings

logger = logging.getLogger(__name__)


class AudioEngine:
    def __init__(self):
        self.model_name = "gemini-2.5-flash-preview-tts"

    async def generate_narration(self, script_data, job_id, mode="publish"):
        """Generate narration using Gemini TTS with gTTS fallback."""
        text = script_data.get("narration", "")
        if not text:
            logger.error(f"Job {job_id}: No narration text found in script_data")
            return None
            
        output_filename = f"{job_id}_narration.wav"
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)

        # Primary: Gemini TTS (with timeout)
        try:
            logger.info(f"Job {job_id}: Attempting Gemini TTS...")
            result = await asyncio.wait_for(
                self._generate_gemini_tts(text, output_path, job_id),
                timeout=120  # 2 minute timeout
            )
            if result:
                return result
        except asyncio.TimeoutError:
            logger.error(f"Job {job_id}: Gemini TTS timed out after 120s. Falling back to gTTS...")
        except Exception as e:
            logger.error(f"Job {job_id}: Gemini TTS failed: {e}. Falling back to gTTS...")

        # Fallback: gTTS (always works, no API quota)
        logger.info(f"Job {job_id}: Using gTTS fallback...")
        return await self._generate_gtts(text, output_path, job_id)

    async def _generate_gemini_tts(self, text, output_path, job_id):
        """Generate high-quality Tamil audio using Gemini TTS."""
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            
            prompt = (
                "You are a professional Tamil narrator for an educational YouTube channel. "
                "Speak clearly with a warm, engaging, and confident tone. "
                "Use natural Tamil pronunciation with moderate pacing. "
                f"\n\n{text}"
            )

            logger.info(f"Job {job_id}: Calling Gemini TTS model {self.model_name}...")
            
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.model_name,
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
