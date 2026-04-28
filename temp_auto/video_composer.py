"""
video_composer.py
=================
Composes the final YouTube-ready video using FFmpeg (free).

Pipeline:
  1. Download a free construction-site background video from Pexels
  2. Place the SadTalker talking-head in the lower-right corner (news-anchor style)
     OR full-screen if no background is available
  3. Burn dual-language ASS captions onto the video
  4. Add intro title card (channel name + day topic)
  5. Output: 1920×1080 H.264 at 8 Mbps → YouTube-optimised

Shorts variant: 1080×1920 (9:16), talking head full-screen, captions same style.
"""

import os
import subprocess
import requests
import shutil
from pathlib import Path
from config import (
    VIDEO_DIR, SHORTS_DIR, CAPTIONS_DIR,
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS,
    SHORT_WIDTH, SHORT_HEIGHT, SHORTS_MAX_SECONDS,
    PEXELS_API_KEY, PEXELS_SEARCH_TERMS,
    BG_VIDEOS_DIR, CHANNEL_NAME
)

os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(SHORTS_DIR, exist_ok=True)
os.makedirs(BG_VIDEOS_DIR, exist_ok=True)

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


# ── Background download (Pexels free API) ────────────────────────────────────

def download_background(day: int, keyword: str = None) -> str | None:
    """Download a construction-site B-roll video from Pexels (free API)."""
    if not PEXELS_API_KEY:
        print("  No Pexels key — using solid background")
        return None

    out_path = os.path.join(BG_VIDEOS_DIR, f"bg_day_{day:02d}.mp4")
    if os.path.exists(out_path):
        return out_path

    search = keyword or PEXELS_SEARCH_TERMS[day % len(PEXELS_SEARCH_TERMS)]
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={search}&orientation=landscape&size=medium&per_page=5"

    try:
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
        videos = data.get("videos", [])
        if not videos:
            return None

        # Pick the highest-quality free version (HD)
        video = videos[0]
        video_files = sorted(
            [f for f in video.get("video_files", []) if f.get("quality") == "hd"],
            key=lambda x: x.get("width", 0), reverse=True
        )
        if not video_files:
            video_files = video.get("video_files", [])
        if not video_files:
            return None

        dl_url = video_files[0]["link"]
        print(f"  Downloading Pexels background: {search}...")
        with requests.get(dl_url, stream=True, timeout=120) as resp:
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
        print(f"  ✓ Background saved: {out_path}")
        return out_path
    except Exception as e:
        print(f"  Background download failed: {e}")
        return None


# ── Video duration helper ─────────────────────────────────────────────────────

def get_duration(path: str) -> float:
    cmd = [FFPROBE, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ── Core composition ──────────────────────────────────────────────────────────

def compose_main_video(
    talking_head_path: str,
    audio_path: str,
    ass_path: str,
    day: int,
    title: str,
    bg_video_path: str = None,
) -> str:
    """
    Compose the full 1920×1080 main video:
      background (looped if shorter than audio) + talking head (right side)
      + intro title card (3s) + dual-language burned captions
    """
    out_path = os.path.join(VIDEO_DIR, f"day_{day:02d}_final.mp4")
    if os.path.exists(out_path):
        print(f"  Video exists: {out_path}")
        return out_path

    audio_dur = get_duration(audio_path)
    th_dur    = get_duration(talking_head_path)
    dur       = max(audio_dur, th_dur)

    if bg_video_path and os.path.exists(bg_video_path):
        # Layout: background (left 70%) + talking head (right 30%, news-anchor)
        filter_complex = _build_composite_filter(bg_video_path, talking_head_path, dur, title, day)
        inputs = [
            FFMPEG, "-y",
            "-stream_loop", "-1", "-i", bg_video_path,   # looped background
            "-i", talking_head_path,
            "-i", audio_path,
        ]
    else:
        # No background — talking head full screen, dark gradient behind
        filter_complex = _build_fullscreen_filter(talking_head_path, dur, title, day)
        inputs = [
            FFMPEG, "-y",
            "-i", talking_head_path,
            "-i", audio_path,
        ]

    # ASS subtitle filter appended
    if os.path.exists(ass_path):
        # Escape path for FFmpeg on all platforms
        esc_ass = ass_path.replace("\\", "/").replace(":", "\\:")
        sub_filter = f",ass='{esc_ass}'"
    else:
        sub_filter = ""

    cmd = inputs + [
        "-filter_complex", filter_complex + sub_filter,
        "-map", "[out]",
        "-map", "2:a" if bg_video_path else "1:a",
        "-t", str(dur),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",           # high quality (lower = better, 18 is near-lossless)
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-movflags", "+faststart",
        out_path
    ]

    print(f"\n  Composing main video ({dur:.0f}s)...")
    subprocess.run(cmd, check=True, timeout=1800)
    print(f"  ✓ Final video: {out_path}")
    return out_path


def _build_composite_filter(bg_path: str, th_path: str, dur: float, title: str, day: int) -> str:
    """
    FFmpeg filter_complex for news-anchor layout:
    • Background scaled to 1920×1080, slightly darkened left side
    • Talking head placed bottom-right (35% width), rounded, with soft shadow
    • 3-second intro title card overlay
    """
    th_w = int(VIDEO_WIDTH * 0.36)   # talking head width
    th_h = int(th_w * 1.25)          # height (portrait ratio)
    th_x = VIDEO_WIDTH - th_w - 40   # right margin
    th_y = VIDEO_HEIGHT - th_h - 40  # bottom margin

    clean_title = title.replace("'", "\\'").replace(":", "\\:")[:50]

    return (
        f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},setsar=1,"
        f"loop=loop=-1:size=200:start=0,trim=duration={dur},"
        f"colorchannelmixer=aa=0.85[bg];"
        f"[1:v]scale={th_w}:{th_h}:force_original_aspect_ratio=increase,"
        f"crop={th_w}:{th_h},setsar=1,trim=duration={dur}[th];"
        f"[bg][th]overlay={th_x}:{th_y}:eof_action=endall[base];"
        # Channel name top-left
        f"[base]drawtext=text='{CHANNEL_NAME}':fontcolor=white:fontsize=36:x=40:y=40:"
        f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"shadowcolor=black:shadowx=2:shadowy=2[titled];"
        # Topic title for first 3 seconds
        f"[titled]drawtext=text='{clean_title}':fontcolor=white:fontsize=48:"
        f"x=(w-text_w)/2:y=h-120:"
        f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"shadowcolor=black:shadowx=3:shadowy=3:enable='lte(t,3)'[out]"
    )


def _build_fullscreen_filter(th_path: str, dur: float, title: str, day: int) -> str:
    """
    FFmpeg filter for full-screen talking head on dark background.
    """
    clean_title = title.replace("'", "\\'").replace(":", "\\:")[:50]
    return (
        f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x0d1117,"
        f"trim=duration={dur},setsar=1[scaled];"
        f"[scaled]drawtext=text='{CHANNEL_NAME}':fontcolor=white:fontsize=36:x=40:y=40:"
        f"shadowcolor=black:shadowx=2:shadowy=2[ch];"
        f"[ch]drawtext=text='{clean_title}':fontcolor=white:fontsize=48:"
        f"x=(w-text_w)/2:y=h-120:"
        f"shadowcolor=black:shadowx=3:shadowy=3:enable='lte(t,3)'[out]"
    )


def compose_short_video(
    talking_head_path: str,
    audio_path: str,
    ass_path: str,
    day: int,
    title: str,
) -> str:
    """
    Compose 1080×1920 YouTube Short:
    Talking head full-screen, vertical, with dual captions.
    Max 58 seconds.
    """
    out_path = os.path.join(SHORTS_DIR, f"day_{day:02d}_short.mp4")
    if os.path.exists(out_path):
        print(f"  Short exists: {out_path}")
        return out_path

    audio_dur = min(get_duration(audio_path), SHORTS_MAX_SECONDS)
    clean_title = title.replace("'", "\\'").replace(":", "\\:")[:40]

    if os.path.exists(ass_path):
        esc_ass = ass_path.replace("\\", "/").replace(":", "\\:")
        sub_filter = f",ass='{esc_ass}'"
    else:
        sub_filter = ""

    filter_complex = (
        f"[0:v]scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={SHORT_WIDTH}:{SHORT_HEIGHT},setsar=1,trim=duration={audio_dur}[scaled];"
        f"[scaled]drawtext=text='{CHANNEL_NAME}':fontcolor=white:fontsize=42:x=30:y=60:"
        f"shadowcolor=black:shadowx=2:shadowy=2[ch];"
        f"[ch]drawtext=text='{clean_title}':fontcolor=white:fontsize=46:"
        f"x=(w-text_w)/2:y=h-240:"
        f"shadowcolor=black:shadowx=3:shadowy=3:enable='lte(t,3)'[out]"
    )

    cmd = [
        FFMPEG, "-y",
        "-i", talking_head_path,
        "-i", audio_path,
        "-filter_complex", filter_complex + sub_filter,
        "-map", "[out]",
        "-map", "1:a",
        "-t", str(audio_dur),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-movflags", "+faststart",
        out_path
    ]

    print(f"\n  Composing Short ({audio_dur:.0f}s)...")
    subprocess.run(cmd, check=True, timeout=600)
    print(f"  ✓ Short: {out_path}")
    return out_path


# ── Full composition entry point ──────────────────────────────────────────────

def compose_all(
    talking_head_path: str,
    short_head_path: str,
    audio_path: str,
    short_audio_path: str,
    ass_path: str,
    short_ass_path: str,
    day: int,
    title: str,
) -> tuple[str, str]:
    """
    Compose both main video and Short.
    Returns (main_video_path, short_video_path).
    """
    bg = download_background(day, title.split()[0])

    main_path  = compose_main_video(talking_head_path, audio_path, ass_path, day, title, bg)
    short_path = compose_short_video(short_head_path, short_audio_path, short_ass_path, day, title)

    return main_path, short_path
