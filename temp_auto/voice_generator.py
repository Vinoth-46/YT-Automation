"""
voice_generator.py
==================
Generates ultra-realistic, human-like voice audio using:

  Coqui XTTS v2  — completely FREE, runs locally
  ● Best free model for natural speech (no robot tone)
  ● Supports English + Tamil natively
  ● Voice cloning: give it 6 seconds of YOUR voice → it sounds like you
  ● Install: pip install TTS
  ● First run: auto-downloads model (~1.8 GB, one-time)

Voice quality ranking (free models):
  1. XTTS v2 with voice clone   ← used here (most human)
  2. XTTS v2 built-in speaker   ← fallback
  3. StyleTTS2                  ← alternative
"""

import os
import re
import numpy as np
import soundfile as sf
from pathlib import Path
from config import (
    TTS_MODEL, TTS_SPEAKER, TTS_LANGUAGE_EN, TTS_LANGUAGE_TA,
    TTS_SAMPLE_RATE, VOICE_CLONE_WAV, AUDIO_DIR
)

os.makedirs(AUDIO_DIR, exist_ok=True)

_tts_engine = None   # loaded once, reused


def _get_engine():
    global _tts_engine
    if _tts_engine is None:
        from TTS.api import TTS
        print("  Loading XTTS v2 (first time: ~1.8 GB download)...")
        _tts_engine = TTS(TTS_MODEL, progress_bar=True, gpu=_has_gpu())
        print("  ✓ XTTS v2 loaded")
    return _tts_engine


def _has_gpu() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def clean_for_tts(text: str) -> str:
    """Strip visual cue markers and markdown so only spoken words remain."""
    text = re.sub(r'\(.*?\)', '', text)          # remove (visual cues)
    text = re.sub(r'\[.*?\]', '', text)          # remove [bracket notes]
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'===.*?===', '', text)
    return text.strip()


def chunk_text(text: str, max_chars: int = 230) -> list[str]:
    """
    Split long text into sentence chunks for XTTS.
    XTTS works best on chunks ≤ 250 chars.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for sent in sentences:
        if len(current) + len(sent) + 1 <= max_chars:
            current = (current + " " + sent).strip()
        else:
            if current:
                chunks.append(current)
            current = sent
    if current:
        chunks.append(current)
    return chunks


def synthesize_english(text: str, day: int, is_short: bool = False) -> str:
    """
    Generate natural English audio with XTTS v2.
    Uses voice cloning if VOICE_CLONE_WAV is set, otherwise built-in speaker.
    Returns path to output WAV file.
    """
    suffix   = "_short" if is_short else ""
    out_path = os.path.join(AUDIO_DIR, f"day_{day:02d}{suffix}_en.wav")
    if os.path.exists(out_path):
        print(f"  Audio exists: {out_path}")
        return out_path

    tts     = _get_engine()
    clean   = clean_for_tts(text)
    chunks  = chunk_text(clean)
    all_wav = []

    print(f"  Synthesising English ({len(chunks)} chunks)...")
    for i, chunk in enumerate(chunks):
        chunk_path = os.path.join(AUDIO_DIR, f"_tmp_en_{day}_{i}.wav")
        if VOICE_CLONE_WAV and os.path.exists(VOICE_CLONE_WAV):
            # Voice clone — sounds exactly like the person in the sample
            tts.tts_to_file(
                text=chunk,
                file_path=chunk_path,
                speaker_wav=VOICE_CLONE_WAV,
                language=TTS_LANGUAGE_EN
            )
        else:
            tts.tts_to_file(
                text=chunk,
                file_path=chunk_path,
                speaker=TTS_SPEAKER,
                language=TTS_LANGUAGE_EN
            )
        wav, sr = sf.read(chunk_path)
        all_wav.append(wav)
        # natural pause between chunks
        all_wav.append(np.zeros(int(sr * 0.25)))
        os.remove(chunk_path)

    merged = np.concatenate(all_wav)
    sf.write(out_path, merged, TTS_SAMPLE_RATE)
    print(f"  ✓ English audio: {out_path} ({len(merged)/TTS_SAMPLE_RATE:.1f}s)")
    return out_path


def synthesize_tamil_intro(title: str, day: int) -> str:
    """
    Synthesise a short Tamil phrase for the intro (e.g. 'வணக்கம்! இன்று நாம் [topic] பற்றி பேசுவோம்.')
    XTTS v2 supports Tamil natively.
    Returns path to WAV.
    """
    out_path = os.path.join(AUDIO_DIR, f"day_{day:02d}_ta_intro.wav")
    if os.path.exists(out_path):
        return out_path

    tamil_greeting = f"வணக்கம்! சிவில் பில்ட் டிவி-க்கு வரவேற்கிறோம். இன்று நாம் {title} பற்றி விரிவாக பேசுவோம்."
    tts = _get_engine()
    if VOICE_CLONE_WAV and os.path.exists(VOICE_CLONE_WAV):
        tts.tts_to_file(text=tamil_greeting, file_path=out_path,
                        speaker_wav=VOICE_CLONE_WAV, language=TTS_LANGUAGE_TA)
    else:
        tts.tts_to_file(text=tamil_greeting, file_path=out_path,
                        speaker=TTS_SPEAKER, language=TTS_LANGUAGE_TA)
    print(f"  ✓ Tamil intro audio: {out_path}")
    return out_path


def merge_audio(en_path: str, ta_intro_path: str, day: int, is_short: bool = False) -> str:
    """
    Prepend Tamil greeting to the English main audio.
    Final audio: [Tamil intro] [silence 0.5s] [English script]
    """
    suffix  = "_short" if is_short else ""
    out     = os.path.join(AUDIO_DIR, f"day_{day:02d}{suffix}_final.wav")
    if os.path.exists(out):
        return out

    ta_wav, ta_sr = sf.read(ta_intro_path)
    en_wav, en_sr = sf.read(en_path)

    # Resample Tamil to match English sr if needed
    if ta_sr != en_sr:
        import librosa
        ta_wav = librosa.resample(ta_wav, orig_sr=ta_sr, target_sr=en_sr)

    silence = np.zeros(int(en_sr * 0.5))
    merged  = np.concatenate([ta_wav, silence, en_wav])
    sf.write(out, merged, en_sr)
    print(f"  ✓ Merged audio: {out} ({len(merged)/en_sr:.1f}s total)")
    return out


def generate_voice(main_script: str, title: str, day: int, is_short: bool = False) -> str:
    """
    Full pipeline: English TTS + Tamil intro → merged final audio.
    Returns final merged audio path.
    """
    print(f"\n[Voice] Day {day} {'Short' if is_short else 'Main'}...")
    en_path      = synthesize_english(main_script, day, is_short)
    ta_path      = synthesize_tamil_intro(title, day)
    final_path   = merge_audio(en_path, ta_path, day, is_short)
    return final_path


# ── Voice clone helper ─────────────────────────────────────────────────────────

def create_voice_clone_sample():
    """
    Prints instructions for recording your own voice sample.
    A 6-second clear WAV recording → XTTS v2 clones your voice perfectly.
    """
    print("""
╔══════════════════════════════════════════════════════════╗
║          VOICE CLONE SETUP (Optional but powerful)       ║
╠══════════════════════════════════════════════════════════╣
║ Record 6-10 seconds of your voice (or any real person):  ║
║  • Speak clearly in a quiet room                         ║
║  • Say: "Welcome to Civil Build TV. Today we will learn  ║
║    about construction techniques for your home."         ║
║  • Save as WAV, 22050 Hz, mono                           ║
║  • Set VOICE_CLONE_WAV=/path/to/sample.wav in .env       ║
║                                                          ║
║ Result: The AI voice will sound EXACTLY like that person ║
╚══════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    create_voice_clone_sample()
    # Quick test
    test = "Welcome to Civil Build TV. Today we talk about concrete mix ratios. If your contractor says M20, you need to know what that means."
    path = generate_voice(test, "Concrete Mix Ratios", day=99, is_short=False)
    print(f"Test audio: {path}")
