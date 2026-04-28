"""
Step 3: Text-to-Speech Generation
Primary: Google Gemini 3.1 Flash TTS (free tier)
Fallback: edge-tts (Microsoft Neural, always free)

Generates natural Tamil voiceover audio for each script.
"""

import asyncio
import io
import json
import logging
import wave
import struct
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)


# ── Gemini TTS (Primary) ─────────────────────────────

def _generate_with_gemini(text: str, output_path: Path) -> bool:
    """
    Generate TTS audio using Gemini 3.1 Flash TTS preview.
    Returns True on success, False on failure.
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        response = client.models.generate_content(
            model=config.GEMINI_TTS_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=config.GEMINI_TTS_VOICE,
                        )
                    )
                ),
            ),
        )

        # Extract audio data from response
        audio_data = response.candidates[0].content.parts[0].inline_data.data
        mime_type = response.candidates[0].content.parts[0].inline_data.mime_type

        if "wav" in mime_type or "pcm" in mime_type:
            # Save as WAV, then convert to MP3 via FFmpeg if needed
            wav_path = output_path.with_suffix(".wav")
            _save_pcm_as_wav(audio_data, wav_path)
            _convert_wav_to_mp3(wav_path, output_path)
            wav_path.unlink(missing_ok=True)  # Clean up WAV
        else:
            # Assume it's already in a usable format
            output_path.write_bytes(audio_data)

        logger.info("✅ Gemini TTS generated: %s", output_path.name)
        return True

    except Exception as e:
        logger.warning("⚠️ Gemini TTS failed: %s", e)
        return False


def _save_pcm_as_wav(pcm_data: bytes, wav_path: Path,
                      sample_rate: int = 24000, channels: int = 1,
                      sample_width: int = 2) -> None:
    """Convert raw PCM bytes to a WAV file."""
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


def _convert_wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    """Convert WAV to MP3 using FFmpeg."""
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-i", str(wav_path),
        "-codec:a", "libmp3lame", "-qscale:a", "2",
        str(mp3_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)


# ── Edge-TTS (Fallback) ──────────────────────────────

async def _generate_with_edge_tts_async(
    text: str,
    output_path: Path,
) -> bool:
    """Generate TTS audio using edge-tts (async). Returns True on success."""
    try:
        import edge_tts

        communicate = edge_tts.Communicate(
            text=text,
            voice=config.EDGE_TTS_VOICE,
            rate=config.EDGE_TTS_RATE,
            pitch=config.EDGE_TTS_PITCH,
        )

        await communicate.save(str(output_path))
        logger.info("✅ edge-tts generated: %s", output_path.name)
        return True

    except Exception as e:
        logger.error("❌ edge-tts failed: %s", e)
        return False


def _generate_with_edge_tts(text: str, output_path: Path) -> bool:
    """Synchronous wrapper for edge-tts."""
    return asyncio.run(_generate_with_edge_tts_async(text, output_path))


# ── Edge-TTS Subtitle Timestamps ─────────────────────

async def _generate_with_timestamps_async(
    text: str,
    output_path: Path,
    subtitle_path: Path,
) -> bool:
    """Generate audio + sentence-level timestamps for subtitle sync."""
    try:
        import edge_tts

        communicate = edge_tts.Communicate(
            text=text,
            voice=config.EDGE_TTS_VOICE,
            rate=config.EDGE_TTS_RATE,
            pitch=config.EDGE_TTS_PITCH,
        )

        subs = []
        with open(str(output_path), "wb") as audio_file:
            async for chunk in communicate.stream():
                chunk_type = chunk.get("type", "")
                if chunk_type == "audio":
                    audio_file.write(chunk["data"])
                elif chunk_type in ("WordBoundary", "SentenceBoundary"):
                    subs.append({
                        "text": chunk.get("text", ""),
                        "offset": chunk.get("offset", 0),       # in ticks (100ns)
                        "duration": chunk.get("duration", 0),    # in ticks
                        "type": chunk_type,
                    })

        # Save subtitle timing data
        subtitle_path.write_text(
            json.dumps(subs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("✅ Generated audio + %d timestamp events", len(subs))
        return True

    except Exception as e:
        logger.error("❌ edge-tts with timestamps failed: %s", e)
        return False


# ── Public API ────────────────────────────────────────

def generate_tts(
    script_text: str,
    day: int,
    force_regenerate: bool = False,
) -> Path:
    """
    Generate TTS audio for a script.

    Priority: Gemini TTS → edge-tts fallback.

    Args:
        script_text: The Tamil script text to convert.
        day: Day number (for output file naming).
        force_regenerate: If True, regenerate even if file exists.

    Returns:
        Path to the generated MP3 file.
    """
    day_dir = config.OUTPUT_DIR / f"day_{day:02d}"
    day_dir.mkdir(parents=True, exist_ok=True)

    audio_path = day_dir / "audio.mp3"
    subtitle_timing_path = day_dir / "word_timestamps.json"

    # Return cached audio if available
    if audio_path.exists() and not force_regenerate:
        logger.info("Using cached audio for day %d", day)
        return audio_path

    logger.info("Generating TTS for day %d (%d chars)...", day, len(script_text))

    # Clean the script text for TTS
    clean_text = _prepare_text_for_tts(script_text)

    # Strategy 1: Try Gemini TTS (Premium)
    if config.GEMINI_API_KEY and config.GEMINI_API_KEY != "your_gemini_api_key_here":
        logger.info("Trying Gemini TTS (Voice: %s) for day %d...", config.GEMINI_TTS_VOICE, day)
        success = _generate_with_gemini(clean_text, audio_path)
        if success:
            # Generate subtitle timestamps separately via edge-tts
            # (Gemini doesn't provide word-level timing)
            logger.info("Generating sync timestamps via edge-tts...")
            asyncio.run(
                _generate_with_timestamps_async(
                    clean_text,
                    day_dir / "audio_edge_sync.mp3",
                    subtitle_timing_path,
                )
            )
            # Clean up sync backup
            (day_dir / "audio_edge_sync.mp3").unlink(missing_ok=True)
            return audio_path

    # Strategy 2: edge-tts with timestamps (Fallback)
    logger.info("Using edge-tts fallback for day %d...", day)
    success = asyncio.run(
        _generate_with_timestamps_async(clean_text, audio_path, subtitle_timing_path)
    )
    if success:
        return audio_path

    # Strategy 3: edge-tts without timestamps
    success = _generate_with_edge_tts(clean_text, audio_path)
    if success:
        return audio_path

    raise RuntimeError(f"All TTS methods failed for day {day}")


def _prepare_text_for_tts(text: str) -> str:
    """Clean and prepare script text for TTS."""
    import re
    # Remove emojis (TTS engines struggle with them)
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map
        "\U0001f1e0-\U0001f1ff"  # flags
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)

    # Remove hashtags
    text = re.sub(r"#\w+", "", text)

    # Clean up extra whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of an audio file in seconds using FFprobe."""
    import subprocess
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with a sample Tamil text
    test_text = (
        "ஒரு சின்ன Mistake... கட்டடமே விழுந்துடும்! "
        "Concrete mix-ல water-cement ratio மிக முக்கியம். "
        "0.45 ratio-க்கு மேல போனா, concrete weak ஆகிடும்."
    )
    audio = generate_tts(test_text, day=0)
    print(f"\n[OK] Test audio saved to: {audio}")
    print(f"Duration: {get_audio_duration(audio):.1f} seconds")
