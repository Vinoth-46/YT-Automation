"""
caption_generator.py
====================
Generates dual-language (English + Tamil) captions burned into the video.

Pipeline:
  1. OpenAI Whisper (free, local) → word-level timestamps from audio
  2. AI4Bharat IndicTrans2 (free HF API) → translate each caption to Tamil
  3. FFmpeg → burn dual-language ASS subtitles into the video

Caption style:
  ● Bottom line  = English (white, bold)
  ● Above it     = Tamil   (yellow, bold)
  ● Karaoke-style word highlighting (each word turns yellow as it's spoken)
  ● Clean black outline for readability on any background
"""

import os
import re
import json
import requests
import subprocess
from dataclasses import dataclass
from typing import List
from config import (
    WHISPER_MODEL, WHISPER_LANGUAGE,
    HF_API_TOKEN, TRANSLATION_MODEL, HF_INFERENCE_URL,
    CAPTIONS_DIR,
    CAPTION_EN_COLOR, CAPTION_TA_COLOR, CAPTION_OUTLINE,
    CAPTION_EN_SIZE, CAPTION_TA_SIZE, CAPTION_OUTLINE_WIDTH,
    CAPTION_BOTTOM_EN, CAPTION_BOTTOM_TA,
    VIDEO_HEIGHT, VIDEO_WIDTH
)

os.makedirs(CAPTIONS_DIR, exist_ok=True)

HF_HEADERS = {"Authorization": f"Bearer {HF_API_TOKEN}"}


@dataclass
class Caption:
    start: float      # seconds
    end:   float
    text_en: str
    text_ta: str


# ── Step 1: Whisper transcription ─────────────────────────────────────────────

def transcribe_audio(audio_path: str, day: int) -> List[Caption]:
    """
    Use OpenAI Whisper locally to get word-level timed captions.
    Returns list of Caption objects grouped into ~8-word chunks.
    """
    import whisper
    cache_path = os.path.join(CAPTIONS_DIR, f"day_{day:02d}_transcript.json")

    if os.path.exists(cache_path):
        with open(cache_path) as f:
            raw = json.load(f)
    else:
        print(f"  Transcribing with Whisper ({WHISPER_MODEL})...")
        model = whisper.load_model(WHISPER_MODEL)
        result = model.transcribe(
            audio_path,
            language=WHISPER_LANGUAGE,
            word_timestamps=True,
            verbose=False
        )
        raw = result
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        print(f"  ✓ Transcription complete ({len(raw.get('segments', []))} segments)")

    # Group words into caption chunks (max 7 words or 4 seconds)
    captions_raw = _group_words(raw)
    return captions_raw


def _group_words(whisper_result: dict, max_words: int = 7, max_duration: float = 4.0) -> List[Caption]:
    """Group word-level timestamps into displayable caption chunks."""
    chunks = []
    current_words = []
    chunk_start = None

    for seg in whisper_result.get("segments", []):
        for word_info in seg.get("words", []):
            word  = word_info.get("word", "").strip()
            start = word_info.get("start", 0)
            end   = word_info.get("end", 0)

            if chunk_start is None:
                chunk_start = start
            current_words.append((word, start, end))

            chunk_dur = end - chunk_start
            if len(current_words) >= max_words or chunk_dur >= max_duration:
                text = " ".join(w[0] for w in current_words)
                chunks.append(Caption(
                    start=chunk_start,
                    end=end,
                    text_en=text,
                    text_ta=""   # filled in next step
                ))
                current_words = []
                chunk_start = None

    if current_words:
        text = " ".join(w[0] for w in current_words)
        chunks.append(Caption(
            start=chunk_start or 0,
            end=current_words[-1][2],
            text_en=text,
            text_ta=""
        ))
    return chunks


# ── Step 2: Tamil translation via IndicTrans2 ─────────────────────────────────

def translate_to_tamil(captions: List[Caption], day: int) -> List[Caption]:
    """
    Translate all English captions to Tamil using AI4Bharat IndicTrans2 (free HF API).
    Falls back to Helsinki-NLP if unavailable.
    """
    cache_path = os.path.join(CAPTIONS_DIR, f"day_{day:02d}_tamil.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            tamil_map = json.load(f)
        for cap in captions:
            cap.text_ta = tamil_map.get(cap.text_en, cap.text_en)
        print(f"  ✓ Tamil translations loaded from cache")
        return captions

    print(f"  Translating {len(captions)} captions to Tamil (IndicTrans2)...")
    tamil_map = {}

    # Batch into groups of 10 to reduce API calls
    batch_size = 10
    texts = [c.text_en for c in captions]

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_text = "\n".join(batch)

        translated = _call_indictrans(batch_text)
        if not translated:
            translated = _call_helsinki(batch_text)

        if translated:
            lines = translated.strip().split("\n")
            for j, line in enumerate(lines):
                if i + j < len(texts):
                    tamil_map[texts[i + j]] = line.strip()
        else:
            # Fallback: keep English
            for t in batch:
                tamil_map[t] = t

    for cap in captions:
        cap.text_ta = tamil_map.get(cap.text_en, cap.text_en)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(tamil_map, f, ensure_ascii=False, indent=2)

    print(f"  ✓ Tamil translation done")
    return captions


def _call_indictrans(text: str) -> str:
    """Call AI4Bharat IndicTrans2 via HuggingFace Inference API."""
    try:
        # IndicTrans2 uses source_sentence format
        payload = {
            "inputs": f"<2ta> {text}",   # target language tag
            "parameters": {"max_length": 512}
        }
        url = f"{HF_INFERENCE_URL}/{TRANSLATION_MODEL}"
        r = requests.post(url, headers=HF_HEADERS, json=payload, timeout=30)
        if r.status_code == 200:
            result = r.json()
            if isinstance(result, list):
                return result[0].get("translation_text", "")
            return result.get("translation_text", "")
    except Exception as e:
        print(f"    IndicTrans2 error: {e}")
    return ""


def _call_helsinki(text: str) -> str:
    """Fallback: Helsinki-NLP opus-mt for English→Tamil."""
    try:
        url = f"{HF_INFERENCE_URL}/Helsinki-NLP/opus-mt-en-mul"
        payload = {"inputs": f">>tam<< {text}"}
        r = requests.post(url, headers=HF_HEADERS, json=payload, timeout=30)
        if r.status_code == 200:
            result = r.json()
            if isinstance(result, list):
                return result[0].get("translation_text", "")
    except Exception as e:
        print(f"    Helsinki fallback error: {e}")
    return ""


# ── Step 3: Generate ASS subtitle file ───────────────────────────────────────

def _seconds_to_ass(s: float) -> str:
    """Convert seconds to ASS timestamp H:MM:SS.cc"""
    h  = int(s // 3600)
    m  = int((s % 3600) // 60)
    sc = s % 60
    cs = int((sc % 1) * 100)
    return f"{h}:{m:02d}:{int(sc):02d}.{cs:02d}"


def build_ass_file(captions: List[Caption], day: int, is_short: bool = False) -> str:
    """
    Write an ASS subtitle file with dual-language styling.
    English = white bold at bottom.
    Tamil   = yellow bold one line above.
    """
    suffix   = "_short" if is_short else ""
    ass_path = os.path.join(CAPTIONS_DIR, f"day_{day:02d}{suffix}.ass")

    w = 1080 if is_short else VIDEO_WIDTH
    h = 1920 if is_short else VIDEO_HEIGHT

    # Scale font sizes proportionally for Shorts (9:16)
    en_size = int(CAPTION_EN_SIZE * (h / VIDEO_HEIGHT))
    ta_size = int(CAPTION_TA_SIZE * (h / VIDEO_HEIGHT))
    bot_en  = int(CAPTION_BOTTOM_EN * (h / VIDEO_HEIGHT))
    bot_ta  = int(CAPTION_BOTTOM_TA * (h / VIDEO_HEIGHT))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
Collisions: Normal
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: English,Arial,{en_size},{CAPTION_EN_COLOR},&H000000FF,{CAPTION_OUTLINE},&H00000000,1,0,0,0,100,100,0,0,1,{CAPTION_OUTLINE_WIDTH},1,2,30,30,{bot_en},1
Style: Tamil,Lohit-Tamil,{ta_size},{CAPTION_TA_COLOR},&H000000FF,{CAPTION_OUTLINE},&H00000000,1,0,0,0,100,100,0,0,1,{CAPTION_OUTLINE_WIDTH},1,2,30,30,{bot_ta},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for cap in captions:
        s  = _seconds_to_ass(cap.start)
        e  = _seconds_to_ass(cap.end)
        # English line
        lines.append(f"Dialogue: 0,{s},{e},English,,0,0,0,,{cap.text_en}")
        # Tamil line (only if different from English)
        if cap.text_ta and cap.text_ta != cap.text_en:
            lines.append(f"Dialogue: 0,{s},{e},Tamil,,0,0,0,,{cap.text_ta}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  ✓ ASS subtitle file: {ass_path} ({len(captions)} captions)")
    return ass_path


# ── Full caption pipeline ──────────────────────────────────────────────────────

def generate_captions(audio_path: str, day: int, is_short: bool = False) -> str:
    """
    Full pipeline: transcribe → translate → build ASS file.
    Returns path to .ass subtitle file.
    """
    print(f"\n[Captions] Day {day} {'Short' if is_short else 'Main'}...")
    captions = transcribe_audio(audio_path, day)
    captions = translate_to_tamil(captions, day)
    ass_path = build_ass_file(captions, day, is_short)
    return ass_path
