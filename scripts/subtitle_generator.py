"""
Step 4c: Subtitle Generator — Premium Tamil Captions
Creates beautifully styled ASS subtitle files for the split-screen layout.

Captions are placed over the BOTTOM HALF (footage area) with:
- Bold Noto Sans Tamil font
- Yellow text with thick black outline + drop shadow (Hormozi style)
- Bottom-center positioning on the footage half
- Short Tamil segments for maximum readability
"""

import json
import logging
import re
from pathlib import Path

import pysubs2

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)


def _ticks_to_ms(ticks: int) -> int:
    """Convert 100-nanosecond ticks to milliseconds."""
    return ticks // 10000


def _clean_text_for_subtitles(text: str) -> str:
    """
    Clean script text for subtitle display.

    Removes:
    - Hashtags (#word)
    - Emojis (broad Unicode ranges)
    - URLs
    - Excess whitespace
    """
    # Remove hashtags (works for both ASCII and Tamil Unicode hashtags)
    text = re.sub(r"#\w+", "", text)

    # Remove emojis (broad Unicode block ranges)
    text = re.sub(
        r"[\U0001F600-\U0001F64F"
        r"\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF"
        r"\U0001F1E0-\U0001F1FF"
        r"\U00002700-\U000027BF"
        r"\U0001F900-\U0001F9FF"
        r"\U00002600-\U000026FF"
        r"\U0000FE00-\U0000FE0F"
        r"\U0001FA00-\U0001FA6F"
        r"\U0001FA70-\U0001FAFF]+",
        "", text,
    )

    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)

    # Normalise whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _create_premium_style(subs: pysubs2.SSAFile) -> None:
    """
    Create the premium Hormozi-style subtitle style.

    Uses borderstyle=1 (Outline + Shadow) so that:
    - outline= and shadow= settings are respected
    - Text has a thick black outline and soft drop shadow
    - No opaque box behind the text

    pysubs2.Color uses (r, g, b, a) where a=0 is fully opaque,
    a=255 is fully transparent (ASS convention).
    """
    style = pysubs2.SSAStyle()

    # Font
    style.fontname = config.SUBTITLE_FONT_NAME
    style.fontsize = config.SUBTITLE_FONT_SIZE
    style.bold = True

    # Colors — pysubs2.Color(r, g, b, a); a=0 → fully opaque
    style.primarycolor = pysubs2.Color(255, 255, 0, 0)     # Bright yellow text
    style.secondarycolor = pysubs2.Color(255, 255, 255, 0)  # White (karaoke fill)
    style.outlinecolor = pysubs2.Color(0, 0, 0, 0)          # Solid black outline
    style.backcolor = pysubs2.Color(0, 0, 0, 100)           # Semi-transparent black shadow

    # Effects
    # borderstyle=1 → Outline + Shadow (outline= and shadow= are active)
    # borderstyle=3 → Opaque box (outline= and shadow= are IGNORED — do NOT use here)
    style.borderstyle = 1
    style.outline = 3   # Thick outline for readability over busy footage
    style.shadow = 1    # Subtle drop shadow for depth

    # Positioning — alignment=2 → bottom-center in ASS numpad layout
    style.alignment = 2
    style.marginv = config.SUBTITLE_MARGIN_BOTTOM
    style.marginl = 60
    style.marginr = 60

    # Match video resolution so positions scale correctly
    subs.info["PlayResX"] = config.VIDEO_WIDTH
    subs.info["PlayResY"] = config.VIDEO_HEIGHT
    subs.info["WrapStyle"] = "0"  # Smart wrapping

    subs.styles["Default"] = style

    # Optional highlight style for future emphasis use
    highlight = style.copy()
    highlight.primarycolor = pysubs2.Color(0, 255, 0, 0)  # Green text
    # fontsize, outline, shadow, etc. are already copied from base style
    subs.styles["Highlight"] = highlight


def _split_into_chunks(text: str, max_chars: int = 20) -> list[str]:
    """
    Split Tamil text into short, fast-paced subtitle chunks.

    Args:
        text: Cleaned Tamil script text.
        max_chars: Maximum characters per chunk (default 20 ≈ 3–4 Tamil words).

    Returns:
        List of text chunks sized for on-screen readability.
    """
    words = text.split()
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for word in words:
        word_len = len(word)
        # +1 accounts for the space between words
        if current_len + word_len + 1 > max_chars and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_len = word_len
        else:
            current_chunk.append(word)
            current_len += word_len + 1

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def generate_subtitles(
    day: int,
    script_text: str,
    audio_duration: float,
    force_regenerate: bool = False,
) -> Path:
    """
    Generate premium Tamil subtitles for a day's content.

    Creates an ASS file with:
    - Short Tamil segments (~3–4 words each)
    - Timing proportional to audio duration
    - Premium Hormozi-style: yellow bold text, black outline + shadow
    - Positioned at bottom of screen (over footage in split-screen)

    Args:
        day: Day number (used for output directory name).
        script_text: The full Tamil script text.
        audio_duration: Total audio duration in seconds.
        force_regenerate: Re-generate even if a cached file exists.

    Returns:
        Path to the generated .ass subtitle file.
    """
    day_dir = config.OUTPUT_DIR / f"day_{day:02d}"
    day_dir.mkdir(parents=True, exist_ok=True)  # FIX: ensure directory exists
    ass_path = day_dir / "subtitles.ass"

    if ass_path.exists() and not force_regenerate:
        logger.info("Using cached subtitles for day %d", day)
        return ass_path

    logger.info("Generating premium Tamil subtitles for day %d", day)

    clean_text = _clean_text_for_subtitles(script_text)
    chunks = _split_into_chunks(clean_text, max_chars=15) or [clean_text]

    total_chars = sum(len(c) for c in chunks)
    duration_ms = int(audio_duration * 1000)

    subs = pysubs2.SSAFile()
    _create_premium_style(subs)

    current_time = 0
    for chunk in chunks:
        chunk_ratio = len(chunk) / max(total_chars, 1)
        chunk_duration = int(duration_ms * chunk_ratio)
        chunk_duration = max(800, min(chunk_duration, 4000))

        event = pysubs2.SSAEvent(
            start=current_time,
            end=current_time + chunk_duration,
            text=chunk.strip(),
            style="Default",
        )
        subs.append(event)
        current_time += chunk_duration

    # Pin last segment end exactly to audio duration to avoid trailing gap
    if subs.events:
        subs.events[-1].end = duration_ms

    subs.save(str(ass_path))

    # Save SRT as a compatibility fallback
    srt_path = day_dir / "subtitles.srt"
    subs.save(str(srt_path), format_="srt")

    logger.info(
        "Generated %d subtitle segments → %s (%.1fs audio)",
        len(chunks), ass_path.name, audio_duration,
    )
    return ass_path


def generate_subtitles_from_timestamps(
    timestamps_path: Path,
    output_path: Path,
    max_chars_per_line: int = 16,
    target_duration: float = None,
) -> Path:
    """
    Generate ASS subtitles from edge-tts word-level timestamps.

    Groups words into natural subtitle segments and optionally scales
    all timings to match a target duration (e.g. after audio speed change).

    Args:
        timestamps_path: Path to JSON file with edge-tts word timestamps.
        output_path: Destination path for the generated .ass file.
        max_chars_per_line: Maximum characters per subtitle segment.
        target_duration: If provided, scale all timings to this duration (seconds).

    Returns:
        Path to the generated .ass file.
    """
    timestamps: list[dict] = json.loads(
        timestamps_path.read_text(encoding="utf-8")
    )

    subs = pysubs2.SSAFile()
    _create_premium_style(subs)

    segments = _group_words_into_segments(timestamps, max_chars_per_line)

    scale_factor = 1.0
    if target_duration and segments:
        original_end_ms = segments[-1]["end_ms"]
        scale_factor = int(target_duration * 1000) / max(original_end_ms, 1)

    for segment in segments:
        event = pysubs2.SSAEvent(
            start=int(segment["start_ms"] * scale_factor),
            end=int(segment["end_ms"] * scale_factor),
            text=segment["text"],
            style="Default",
        )
        subs.append(event)

    subs.save(str(output_path))
    logger.info(
        "Generated subtitles: %d segments → %s", len(segments), output_path.name
    )
    return output_path


def _group_words_into_segments(
    timestamps: list[dict],
    max_chars: int = 16,
) -> list[dict]:
    """
    Group word-level timestamps into natural subtitle segments.

    A new segment is started when:
    - Adding the next word would exceed max_chars, OR
    - The current or next word ends with a sentence-ending punctuation mark.

    Args:
        timestamps: List of dicts with keys: text, offset (ticks), duration (ticks).
        max_chars: Maximum characters per segment.

    Returns:
        List of dicts with keys: start_ms, end_ms, text.
    """
    # FIX: removed duplicate "?" from the punctuation set
    SENTENCE_END_CHARS = (".", "!", "?", "।")

    segments: list[dict] = []
    current_words: list[str] = []
    current_text = ""
    current_start: int | None = None

    for word_data in timestamps:
        word = word_data.get("text", "")
        offset = word_data.get("offset", 0)
        duration = word_data.get("duration", 0)

        word_start_ms = _ticks_to_ms(offset)
        word_end_ms = _ticks_to_ms(offset + duration)

        if current_start is None:
            current_start = word_start_ms

        test_text = f"{current_text} {word}".strip() if current_text else word

        should_break = (
            len(test_text) > max_chars
            or word.endswith(SENTENCE_END_CHARS)
            or (current_text and current_text.endswith(SENTENCE_END_CHARS))
        )

        if should_break and current_text:
            segments.append({
                "start_ms": current_start,
                "end_ms": word_start_ms,
                "text": current_text.strip(),
            })
            current_text = word
            current_start = word_start_ms
        else:
            current_text = test_text

        current_end_ms = word_end_ms  # FIX: local variable, updated each iteration

    # Flush remaining words
    if current_text:
        segments.append({
            "start_ms": current_start,
            "end_ms": current_end_ms,
            "text": current_text.strip(),
        })

    return segments


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_script = (
        "நீங்க கட்டும் வீட்ல காங்கிரீட் ரேஷியோ தப்பா போட்டா "
        "10 வருஷத்துல வீடு விழும்! ஒரு நல்ல காங்கிரீட்டுக்கு "
        "சிமெண்ட், மணல், அக்ரிகேட் — 1:1.5:3 ரேஷியோல போடணும்."
    )

    # FIX: renamed from 'srt' — generate_subtitles returns the .ass path, not .srt
    ass_path = generate_subtitles(
        day=0,
        script_text=test_script,
        audio_duration=25.0,
        force_regenerate=True,
    )

    print(f"\nASS subtitles saved to : {ass_path}")
    print(f"SRT fallback saved to  : {ass_path.with_suffix('.srt')}")
    print(f"Segments generated     : check log output above")