"""
talking_head.py
===============
Generates a REALISTIC HUMAN talking-head video using SadTalker (free, open-source).

What SadTalker does:
  • Takes ONE photo of a real/AI-generated person
  • Takes audio (your XTTS voice)
  • Outputs a video of that person speaking with accurate lip-sync,
    natural blinking, head movement, and facial expressions
  • Output is enhanced with RestoreFormer/CodeFormer (face super-resolution)
    making it indistinguishable from a real person on camera

SadTalker setup (run ONCE):
  git clone https://github.com/OpenTalker/SadTalker.git
  cd SadTalker
  pip install -r requirements.txt
  bash scripts/download_models.sh      # ~2 GB weights, free

Avatar photo options (all free):
  Option A: https://thispersondoesnotexist.com  (AI face, refresh for new person)
  Option B: Generate with Stable Diffusion locally (any realistic portrait)
  Option C: Use your own photo → voice clone + talking head = you on screen
  
Tip: Use a photo with neutral background, good lighting, front-facing, 512×512+
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from config import (
    SADTALKER_DIR, AVATAR_PHOTO, SADTALKER_ENHANCER,
    SADTALKER_STILL_MODE, SADTALKER_EXP_SCALE,
    VIDEO_FPS, FRAMES_DIR, DATA_DIR
)

os.makedirs(FRAMES_DIR, exist_ok=True)


def is_sadtalker_installed() -> bool:
    return os.path.isdir(SADTALKER_DIR) and os.path.exists(
        os.path.join(SADTALKER_DIR, "inference.py")
    )


def print_install_guide():
    print("""
╔══════════════════════════════════════════════════════════════╗
║          SadTalker — One-time Install (Free)                 ║
╠══════════════════════════════════════════════════════════════╣
║  git clone https://github.com/OpenTalker/SadTalker.git       ║
║  cd SadTalker                                                ║
║  pip install -r requirements.txt                             ║
║  bash scripts/download_models.sh                             ║
║                                                              ║
║  Then set in .env:                                           ║
║    SADTALKER_DIR=/path/to/SadTalker                          ║
║    AVATAR_PHOTO=/path/to/your/presenter_photo.jpg            ║
╚══════════════════════════════════════════════════════════════╝
""")


def generate_talking_head(
    audio_path: str,
    day: int,
    is_short: bool = False,
    avatar_photo: str = None
) -> str:
    """
    Run SadTalker to produce a talking-head video from audio + portrait photo.
    Returns path to the output MP4.

    Parameters
    ----------
    audio_path   : path to merged audio (English + Tamil intro)
    day          : content day number (used for output filename)
    is_short     : True → 9:16 crop for Shorts
    avatar_photo : override default avatar photo
    """
    if not is_sadtalker_installed():
        print_install_guide()
        raise RuntimeError("SadTalker not installed. See guide above.")

    photo = avatar_photo or AVATAR_PHOTO
    if not os.path.exists(photo):
        raise FileNotFoundError(
            f"Avatar photo not found: {photo}\n"
            "Download a face from https://thispersondoesnotexist.com and save it."
        )

    suffix     = "_short" if is_short else ""
    result_dir = os.path.join(DATA_DIR, "sadtalker_out", f"day_{day:02d}{suffix}")
    os.makedirs(result_dir, exist_ok=True)

    # ── Build SadTalker command ───────────────────────────────────────────────
    cmd = [
        sys.executable,
        os.path.join(SADTALKER_DIR, "inference.py"),
        "--driven_audio",    audio_path,
        "--source_image",    photo,
        "--result_dir",      result_dir,
        "--enhancer",        SADTALKER_ENHANCER,   # RestoreFormer = best realism
        "--expression_scale", str(SADTALKER_EXP_SCALE),
        "--size",            "512",                 # 512 → enhanced to 1080p after
        "--batch_size",      "2",
        "--face3dvis",
    ]

    if SADTALKER_STILL_MODE:
        cmd.append("--still")                      # minimal head movement
    else:
        cmd.append("--preprocess")
        cmd.append("full")                         # full-body preprocess

    print(f"\n  Running SadTalker for Day {day} {'Short' if is_short else 'Main'}...")
    print(f"  Command: {' '.join(cmd[:5])} ...")

    result = subprocess.run(
        cmd,
        cwd=SADTALKER_DIR,
        capture_output=False,
        text=True,
        timeout=1200   # 20 min max
    )

    if result.returncode != 0:
        raise RuntimeError(f"SadTalker failed (exit {result.returncode})")

    # ── Find the output file ──────────────────────────────────────────────────
    mp4_files = list(Path(result_dir).glob("*.mp4"))
    if not mp4_files:
        raise RuntimeError(f"SadTalker produced no MP4 in {result_dir}")

    raw_video = str(sorted(mp4_files)[-1])   # latest file
    print(f"  ✓ Talking head: {raw_video}")
    return raw_video


def enhance_face_video(input_path: str, output_path: str) -> str:
    """
    Run GFPGAN / CodeFormer to upscale and enhance face details.
    This is what makes the face look truly photorealistic.
    SadTalker bundles these — no extra install needed.
    """
    enhancer_script = os.path.join(SADTALKER_DIR, "src", "utils", "face_enhancer.py")
    if not os.path.exists(enhancer_script):
        print("  Face enhancer script not found — skipping enhancement")
        shutil.copy(input_path, output_path)
        return output_path

    cmd = [
        sys.executable, enhancer_script,
        "--input",    input_path,
        "--output",   output_path,
        "--enhancer", SADTALKER_ENHANCER,
        "--bg_upsampler", "realesrgan",   # also upscales background
    ]
    subprocess.run(cmd, cwd=SADTALKER_DIR, check=True, timeout=300)
    print(f"  ✓ Face enhanced: {output_path}")
    return output_path


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def trim_to_duration(input_path: str, output_path: str, max_seconds: float) -> str:
    """Trim a video to max_seconds using FFmpeg (for Shorts ≤ 58s)."""
    dur = get_video_duration(input_path)
    if dur <= max_seconds:
        shutil.copy(input_path, output_path)
        return output_path
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-t", str(max_seconds),
        "-c", "copy",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"  ✓ Trimmed to {max_seconds}s: {output_path}")
    return output_path
