import os
import logging
import aiofiles
from google import genai
from google.genai import types
from core.config import settings

logger = logging.getLogger(__name__)

class AudioEngine:
    def __init__(self, model_name="gemini-2.0-flash-exp"):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = model_name

    async def generate_audio(self, text, output_path, voice_name="Puck"):
        """Generate high-quality Tamil audio using Gemini's native TTS capabilities."""
        try:
            config = types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                    )
                )
            )

            # Note: The SDK might be synchronous or have specific async wrappers.
            # Using client.models.generate_content (Assuming synchronous for simplicity in prototype, 
            # or wrapping in run_in_executor if needed)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=text,
                config=config
            )

            # Find the audio part in the response
            audio_bytes = None
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    audio_bytes = part.inline_data.data
                    break
            
            if audio_bytes:
                async with aiofiles.open(output_path, "wb") as f:
                    await f.write(audio_bytes)
                logger.info(f"Audio saved to {output_path}")
                return True
            else:
                logger.error("No audio bytes found in response")
                return False

        except Exception as e:
            logger.error(f"Failed to generate Gemini audio: {e}")
            return False

    async def generate_narration(self, script_data, job_id):
        """Orchestrate narration generation for a full script."""
        narration_text = script_data.get("narration", "")
        if not narration_text:
            return None
        
        output_filename = f"{job_id}_narration.wav"
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
        
        success = await self.generate_audio(narration_text, output_path)
        return output_path if success else None
