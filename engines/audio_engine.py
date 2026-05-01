import os
import logging
import asyncio
from google import genai
from google.genai import types
from core.config import settings

logger = logging.getLogger(__name__)

# Initialize the Gemini client
gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

class AudioEngine:
    def __init__(self):
        self.model_name = "gemini-3.1-flash-tts-preview"

    async def generate_narration(self, script_data, job_id, mode="publish"):
        """Generate narration using Gemini TTS with gTTS fallback."""
        text = script_data.get("narration", "")
        output_filename = f"{job_id}_narration.wav"
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)

        # Primary: Gemini TTS
        try:
            result = await self._generate_gemini_tts(text, output_path)
            if result:
                return result
        except Exception as e:
            logger.error(f"Gemini TTS failed: {e}. Falling back to gTTS...")

        # Fallback: gTTS
        return await self._generate_gtts(text, output_path)

    async def _generate_gemini_tts(self, text, output_path):
        """Generate high-quality Tamil audio using Gemini TTS."""
        try:
            # Build the prompt with audio profile for Tamil narration
            prompt = (
                "You are a professional Tamil narrator for an educational YouTube channel. "
                "Speak clearly with a warm, engaging, and confident tone. "
                "Use natural Tamil pronunciation with moderate pacing. "
                f"\n\n{text}"
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: gemini_client.models.generate_content(
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
            )

            # Extract audio data from response
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    audio_data = part.inline_data.data
                    mime_type = part.inline_data.mime_type

                    # Gemini returns audio as raw bytes (typically PCM/WAV)
                    # Write directly if WAV, or convert if needed
                    if "wav" in mime_type:
                        with open(output_path, "wb") as f:
                            f.write(audio_data)
                    else:
                        # Save as raw temp file and convert to WAV via ffmpeg
                        temp_path = output_path.replace(".wav", ".raw")
                        with open(temp_path, "wb") as f:
                            f.write(audio_data)

                        # For Gemini l16 audio, we must specify the input format
                        input_args = ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", temp_path]
                        output_args = [output_path]
                        
                        process = await asyncio.create_subprocess_exec(
                            *input_args, *output_args,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        _, stderr = await process.communicate()

                        if os.path.exists(temp_path):
                            os.remove(temp_path)

                        if process.returncode != 0:
                            logger.error(f"FFmpeg conversion failed for Gemini audio: {stderr.decode()}")
                            return None

                    if os.path.exists(output_path):
                        logger.info(f"Gemini TTS audio generated at {output_path}")
                        return output_path
                    else:
                        logger.error(f"Gemini TTS output file not found at {output_path}")
                        return None

            logger.error("No audio data in Gemini TTS response")
            return None
        except Exception as e:
            logger.error(f"Gemini TTS generation error: {e}")
            raise

    async def _generate_gtts(self, text, output_path):
        """Generate audio using Google Text-to-Speech (gTTS) as fallback."""
        try:
            from gtts import gTTS

            # gTTS supports Tamil natively
            tts = gTTS(text=text, lang="ta", slow=False)

            mp3_path = output_path.replace(".wav", ".mp3")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: tts.save(mp3_path))

            # Convert MP3 to WAV using ffmpeg for compatibility
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", mp3_path,
                "-ar", "22050", "-ac", "1", output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()

            if process.returncode == 0:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
                logger.info(f"Fallback audio generated using gTTS at {output_path}")
                return output_path
            else:
                logger.error(f"FFmpeg conversion failed: {stderr.decode()}")
                # Use mp3 directly if ffmpeg fails
                if os.path.exists(mp3_path):
                    os.rename(mp3_path, output_path)
                    return output_path
                return None
        except Exception as e:
            logger.error(f"gTTS fallback error: {e}")
            return None
