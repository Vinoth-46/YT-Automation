"""
Step 4b: Video Assembler — Split-Screen Layout
Combines avatar (top half) + stock footage (bottom half) + TTS audio +
subtitles + BGM into a production-ready YouTube Shorts video (1080x1920).

Layout:
  ┌────────────────┐
  │   AVATAR HEAD   │  ← Top 50% (960px) — Wav2Lip talking head
  │   (lip-synced)  │
  ├────────────────┤
  │  STOCK FOOTAGE  │  ← Bottom 50% (960px) — Related visuals
  │  + CAPTIONS     │  ← Tamil subtitles overlaid here
  └────────────────┘

Uses FFmpeg for all processing.
"""

import os
import json
import logging
import subprocess
import random
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)


def _get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using FFprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def _get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Get video width and height using FFprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            str(video_path),
        ],
        capture_output=True, text=True,
    )
    parts = result.stdout.strip().split(",")
    return int(parts[0]), int(parts[1])


def _prepare_clip_ffmpeg(
    input_path: Path,
    output_path: Path,
    target_duration: float,
    target_width: int,
    target_height: int,
    animation: str = "static",
) -> bool:
    """
    Prepare a single footage clip: crop to target aspect ratio,
    scale to target dimensions, apply animation, trim to duration.
    """
    try:
        w, h = _get_video_dimensions(input_path)
        clip_duration = _get_video_duration(input_path)

        # Calculate crop for target aspect ratio
        target_ratio = target_width / target_height
        current_ratio = w / h

        if current_ratio > target_ratio:
            new_w = int(h * target_ratio)
            crop_x = (w - new_w) // 2
            crop_filter = f"crop={new_w}:{h}:{crop_x}:0"
        else:
            new_h = int(w / target_ratio)
            crop_y = (h - new_h) // 2
            crop_filter = f"crop={w}:{new_h}:0:{crop_y}"

        scale_filter = f"scale={target_width}:{target_height}"

        # Animation filter
        if animation == "static":
            # Use subtle zoom-in for static shots to avoid 'frozen' look
            animation = "zoom_in"

        anim_filter = _get_animation_filter(
            animation, target_duration, target_width, target_height
        )

        filters = [crop_filter, scale_filter]
        if anim_filter:
            filters.append(anim_filter)

        filter_chain = ",".join(filters)

        # Detect if input is image or video for proper looping
        is_image = input_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
        
        cmd = ["ffmpeg", "-y"]
        if is_image:
            cmd.extend(["-loop", "1"])
        else:
            # Loop videos that are shorter than the target duration
            cmd.extend(["-stream_loop", "-1"])

        cmd.extend([
            "-i", str(input_path),
            "-t", str(target_duration),
            "-vf", filter_chain,
            "-r", str(config.VIDEO_FPS),
            "-an",
            "-c:v", config.VIDEO_CODEC,
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ])

        subprocess.run(cmd, capture_output=True, check=True)
        return True

    except Exception as e:
        logger.error("Failed to prepare clip %s: %s", input_path.name, e)
        return False


def _get_animation_filter(
    animation: str, duration: float, width: int, height: int
) -> str | None:
    """Generate FFmpeg filter for Ken Burns-style animation."""
    total_frames = int(duration * config.VIDEO_FPS)

    if animation == "zoom_in":
        # Slow zoom over entire duration
        return (
            f"zoompan=z='1.0+(on/{total_frames})*0.15':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d={total_frames}:"
            f"s={width}x{height}:fps={config.VIDEO_FPS}"
        )
    elif animation == "zoom_out":
        return (
            f"zoompan=z='1.15-(on/{total_frames})*0.15':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d={total_frames}:"
            f"s={width}x{height}:fps={config.VIDEO_FPS}"
        )
    elif animation == "pan_left":
        return (
            f"zoompan=z=1.15:x='iw*0.1*(1-on/{total_frames})':"
            f"y='ih/2-(ih/zoom/2)':d={total_frames}:"
            f"s={width}x{height}:fps={config.VIDEO_FPS}"
        )
    elif animation == "pan_right":
        return (
            f"zoompan=z=1.15:x='iw*0.1*(on/{total_frames})':"
            f"y='ih/2-(ih/zoom/2)':d={total_frames}:"
            f"s={width}x{height}:fps={config.VIDEO_FPS}"
        )
    return None


def _create_color_clip(
    output_path: Path,
    duration: float,
    width: int,
    height: int,
    color: str = "0x1a1a2e",
) -> None:
    """Create a solid color clip as fallback when footage is missing."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", (
            f"color=c={color}:s={width}x{height}:"
            f"d={duration}:r={config.VIDEO_FPS}"
        ),
        "-c:v", config.VIDEO_CODEC,
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def _prepare_avatar_video(
    avatar_path: Path,
    output_path: Path,
    target_duration: float,
) -> Path:
    """
    Prepare the avatar video for the top half of the split screen.
    Scales to 1080 x AVATAR_HEIGHT (960px), pads/crops as needed.
    """
    aw = config.VIDEO_WIDTH
    ah = config.AVATAR_HEIGHT

    cmd = [
        "ffmpeg", "-y",
        "-i", str(avatar_path),
        "-t", str(target_duration),
        "-vf", (
            f"scale={aw}:{ah}:force_original_aspect_ratio=decrease,"
            f"pad={aw}:{ah}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1"
        ),
        "-r", str(config.VIDEO_FPS),
        "-an",
        "-c:v", config.VIDEO_CODEC,
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Avatar prep failed: %s", result.stderr[-500:])
        raise RuntimeError("Failed to prepare avatar video")

    return output_path


def assemble_video(
    day: int,
    visual_plan: dict,
    audio_path: Path,
    subtitle_path: Path,
    footage_paths: list[Path],
    avatar_path: Path = None,
    force_regenerate: bool = False,
) -> Path:
    """
    Assemble the final YouTube Shorts video in split-screen format.

    Layout:
      Top half (960px):  Avatar talking head
      Bottom half (960px): Stock footage with captions

    Steps:
    1. Prepare each footage clip (crop to bottom-half size, animate)
    2. Concatenate footage clips
    3. Prepare avatar video (scale to top-half size)
    4. Stack avatar (top) + footage (bottom) vertically
    5. Add TTS audio + background music
    6. Burn subtitles over the bottom half
    7. Add channel watermark

    Args:
        day: Day number.
        visual_plan: Visual plan dict with scenes.
        audio_path: Path to TTS audio file.
        subtitle_path: Path to .ass subtitle file.
        footage_paths: List of downloaded footage clips.
        avatar_path: Optional path to Wav2Lip talking head video.
        force_regenerate: Regenerate even if exists.

    Returns:
        Path to the final video file.
    """
    day_dir = config.OUTPUT_DIR / f"day_{day:02d}"
    final_output = day_dir / "final_video.mp4"
    temp_dir = day_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    if final_output.exists() and not force_regenerate:
        logger.info("Using cached final video for day %d", day)
        return final_output

    logger.info("🎬 Assembling split-screen video for day %d...", day)

    # Get audio duration
    audio_duration = _get_video_duration(audio_path)
    total_duration = min(audio_duration + 1.0, config.VIDEO_MAX_DURATION)

    scenes = visual_plan.get("scenes", [])
    fw = config.VIDEO_WIDTH
    
    # Support Footage-Only Mode
    is_footage_only = getattr(config, "VIDEO_MODE", "avatar") == "footage_only"
    fh = config.VIDEO_HEIGHT if is_footage_only else config.FOOTAGE_HEIGHT

    # ── Step 1: Prepare footage clips ──
    prepared_clips = []
    for i, scene in enumerate(scenes):
        scene_duration = scene.get("duration_sec", 8)
        animation = scene.get("animation", "static")

        if i < len(footage_paths) and footage_paths[i].exists():
            input_clip = footage_paths[i]
        else:
            input_clip = temp_dir / f"placeholder_{i}.mp4"
            _create_color_clip(input_clip, scene_duration, fw, fh)

        prepared_path = temp_dir / f"footage_{i:02d}.mp4"
        success = _prepare_clip_ffmpeg(
            input_clip, prepared_path, scene_duration, fw, fh, animation
        )

        if success:
            prepared_clips.append(prepared_path)
        else:
            fallback = temp_dir / f"fallback_{i:02d}.mp4"
            _create_color_clip(fallback, scene_duration, fw, fh)
            prepared_clips.append(fallback)

    # ── Step 2: Concatenate footage clips ─────────────────
    concat_file = temp_dir / "concat_list.txt"
    footage_concat = temp_dir / "footage_concat.mp4"

    with open(concat_file, "w", encoding="utf-8") as f:
        for clip in prepared_clips:
            f.write(f"file '{clip}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c:v", config.VIDEO_CODEC,
        "-pix_fmt", "yuv420p",
        "-t", str(total_duration),
        str(footage_concat),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    logger.info("Concatenated %d footage clips", len(prepared_clips))

    if is_footage_only:
        stacked_video = footage_concat
        logger.info("Footage-only mode: using full-screen footage")
    else:
        # ── Step 3: Prepare avatar video (top half) ───────────
        has_avatar = avatar_path is not None and avatar_path.exists()
        avatar_prepared = temp_dir / "avatar_prepared.mp4"

        if has_avatar:
            _prepare_avatar_video(avatar_path, avatar_prepared, total_duration)
            logger.info("Prepared avatar for top half")
        else:
            # No avatar — create a dark placeholder for top half
            logger.warning("No avatar video. Using placeholder for top half.")
            _create_color_clip(
                avatar_prepared, total_duration,
                config.VIDEO_WIDTH, config.AVATAR_HEIGHT, color="0x0d1117"
            )

        # ── Step 4: Stack avatar + footage vertically ─────────
        stacked_video = temp_dir / "stacked.mp4"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(avatar_prepared),
            "-i", str(footage_concat),
            "-filter_complex", (
                f"[0:v][1:v]vstack=inputs=2"
            ),
            "-c:v", config.VIDEO_CODEC,
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-t", str(total_duration),
            str(stacked_video),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info("Stacked avatar + footage into split-screen")

    # ── Step 5: Add audio + subtitles + BGM + watermark ───
    # Build the complex FFmpeg filter graph
    inputs = ["-i", str(stacked_video), "-i", str(audio_path)]
    filter_parts = []
    input_count = 2

    # Add BGM if available
    bgm_path = config.BGM_PATH
    has_bgm = bgm_path.exists()
    if has_bgm:
        inputs.extend(["-i", str(bgm_path)])
        bgm_input = input_count
        input_count += 1

    # ── Video filters ──
    video_filters = []
    base_v = "0:v"

    # Add a subtle dark gradient over the bottom for caption readability
    video_filters.append(
        f"[{base_v}]drawbox=x=0:y=ih-200:w=iw:h=200:"
        f"color=black@0.5:t=fill[v_grad]"
    )
    base_v = "v_grad"

    # Burn subtitles
    if subtitle_path.exists() and subtitle_path.stat().st_size > 0:
        import shutil
        simple_ass = temp_dir / "subs.ass"
        shutil.copy2(subtitle_path, simple_ass)
        ass_escaped = str(simple_ass).replace("\\", "/").replace(":", "\\:")
        video_filters.append(f"[{base_v}]ass='{ass_escaped}'[v_sub]")
        base_v = "v_sub"

    # Add watermark if available
    watermark_path = config.WATERMARK_PATH
    if watermark_path.exists():
        inputs.extend(["-i", str(watermark_path)])
        watermark_input = input_count
        input_count += 1
        # Place watermark in the top-right corner of the avatar area
        video_filters.append(
            f"[{base_v}][{watermark_input}:v]"
            f"overlay=W-w-20:20[v_wm]"
        )
        base_v = "v_wm"

    video_filter_str = ";".join(video_filters)

    # ── Audio mixing ──
    if has_bgm:
        audio_filter = (
            f"[1:a]volume=0dB[voice];"
            f"[{bgm_input}:a]volume={config.BGM_VOLUME_DB}dB,"
            f"afade=t=in:st=0:d=1,afade=t=out:st={total_duration - 1}:d=1[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=shortest[aout]"
        )
    else:
        audio_filter = "[1:a]volume=0dB[aout]"

    # ── Final assembly command ──
    cmd = ["ffmpeg", "-y"]
    cmd.extend(inputs)
    cmd.extend([
        "-t", str(total_duration),
        "-filter_complex", f"{video_filter_str};{audio_filter}",
        "-map", f"[{base_v}]",
        "-map", "[aout]",
        "-c:v", config.VIDEO_CODEC,
        "-preset", "medium",
        "-b:v", config.VIDEO_BITRATE,
        "-c:a", config.VIDEO_AUDIO_CODEC,
        "-b:a", config.VIDEO_AUDIO_BITRATE,
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-movflags", "+faststart",
        str(final_output),
    ])

    try:
        # Create a temporary fonts.conf with absolute paths for libass
        font_dir = config.ASSETS_DIR / "fonts"
        fonts_conf_path = temp_dir / "fonts.conf"
        fonts_conf_content = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
    <dir>{font_dir.absolute()}</dir>
    <dir>/usr/share/fonts</dir>
    <dir>/usr/local/share/fonts</dir>
</fontconfig>"""
        fonts_conf_path.write_text(fonts_conf_content)

        env = os.environ.copy()
        env["FONTCONFIG_FILE"] = str(fonts_conf_path.absolute())
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
        logger.info("✅ Final split-screen video assembled: %s", final_output.name)
    except subprocess.CalledProcessError as e:
        logger.error("FFmpeg failed: %s", e.stderr[-500:] if e.stderr else "unknown")
        logger.info("Retrying with simpler pipeline...")
        final_output = _assemble_simple(
            stacked_video, audio_path, total_duration, final_output
        )

    # ── Cleanup ──
    _cleanup_temp(temp_dir)

    return final_output


def _assemble_simple(
    video_path: Path,
    audio_path: Path,
    duration: float,
    output_path: Path,
) -> Path:
    """Simple assembly without subtitle burning (fallback)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-t", str(duration),
        "-c:v", config.VIDEO_CODEC,
        "-c:a", config.VIDEO_AUDIO_CODEC,
        "-b:a", config.VIDEO_AUDIO_BITRATE,
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    logger.info("✅ Simple video assembled (no subs): %s", output_path.name)
    return output_path


def _cleanup_temp(temp_dir: Path) -> None:
    """Remove temporary processing files."""
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info("Cleaned up temp directory")
    except Exception:
        pass


def validate_video(video_path: Path) -> dict:
    """Validate the final video meets YouTube Shorts requirements."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "stream=width,height,duration,codec_name",
            "-show_entries", "format=duration,size",
            "-of", "json",
            str(video_path),
        ],
        capture_output=True, text=True,
    )

    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    fmt = info.get("format", {})

    video_stream = next(
        (s for s in streams if s.get("codec_name") in ["h264", "hevc"]), None
    )

    validation = {
        "file": str(video_path),
        "duration_sec": float(fmt.get("duration", 0)),
        "file_size_mb": int(fmt.get("size", 0)) / 1024 / 1024,
        "width": int(video_stream.get("width", 0)) if video_stream else 0,
        "height": int(video_stream.get("height", 0)) if video_stream else 0,
        "codec": video_stream.get("codec_name", "unknown") if video_stream else "unknown",
        "is_vertical": False,
        "is_shorts_length": False,
        "is_valid": False,
    }

    validation["is_vertical"] = validation["height"] > validation["width"]
    validation["is_shorts_length"] = validation["duration_sec"] <= config.VIDEO_MAX_DURATION
    validation["is_valid"] = (
        validation["is_vertical"]
        and validation["is_shorts_length"]
        and validation["width"] >= 1080
    )

    return validation


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Video assembler module loaded. Use assemble_video() to create videos.")
