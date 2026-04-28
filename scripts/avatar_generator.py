"""
Step 4d: Avatar Generator — Wav2Lip
Generates a lip-synced talking head video from a static avatar image
and TTS audio using the Wav2Lip model.

Wav2Lip produces significantly more accurate lip sync than SadTalker,
especially for non-English (Tamil) audio.

Designed to run on Google Colab with a T4 GPU.
"""

import os
import sys
import subprocess
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Wav2Lip Paths (Colab) ────────────────────────────
WAV2LIP_DIR = "/content/Wav2Lip"
CHECKPOINTS_DIR = os.path.join(WAV2LIP_DIR, "checkpoints")
FACE_DETECTION_DIR = os.path.join(WAV2LIP_DIR, "face_detection", "detection", "sfd")

# Model download URLs
WAV2LIP_GAN_URL = "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip_gan.pth"
WAV2LIP_URL = "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip.pth"
S3FD_URL = "https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth"


def is_wav2lip_installed() -> bool:
    """Check if Wav2Lip is cloned and has the required checkpoint."""
    return (
        os.path.isdir(WAV2LIP_DIR)
        and os.path.exists(os.path.join(WAV2LIP_DIR, "inference.py"))
        and os.path.exists(os.path.join(CHECKPOINTS_DIR, "wav2lip_gan.pth"))
    )


def install_wav2lip() -> bool:
    """
    Install Wav2Lip and its dependencies on Colab.
    Downloads model checkpoints automatically.
    Returns True if installation succeeds.
    """
    logger.info("📦 Installing Wav2Lip...")

    try:
        # Step 1: Clone repository
        if not os.path.isdir(WAV2LIP_DIR):
            logger.info("Cloning Wav2Lip repository...")
            subprocess.run(
                ["git", "clone", "https://github.com/Rudrabha/Wav2Lip.git", WAV2LIP_DIR],
                check=True, capture_output=True, text=True,
            )
        
        # Step 2: Install dependencies (modern compatible versions)
        logger.info("Installing Wav2Lip dependencies...")
        deps = [
            "librosa>=0.9.0",
            "opencv-contrib-python>=4.2.0,<4.10.0",
            "opencv-python>=4.2.0,<4.10.0",
            "tqdm",
            "numba",
            "numpy<2.0",
        ]
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet"] + deps,
            check=True, capture_output=True, text=True,
        )

        # Step 3: Download model checkpoints
        os.makedirs(CHECKPOINTS_DIR, exist_ok=True)

        gan_path = os.path.join(CHECKPOINTS_DIR, "wav2lip_gan.pth")
        if os.path.exists(gan_path) and os.path.getsize(gan_path) < 100 * 1024 * 1024:
            logger.info("Found invalid/corrupt wav2lip_gan.pth (too small). Removing it...")
            os.remove(gan_path)

        if not os.path.exists(gan_path):
            logger.info("Downloading wav2lip_gan.pth checkpoint (~440 MB)...")
            subprocess.run(
                ["wget", "-q", "-c", WAV2LIP_GAN_URL, "-O", gan_path],
                check=True, capture_output=True, text=True,
            )
            
            # Verify file size is not an HTML error page
            if os.path.getsize(gan_path) < 100 * 1024 * 1024:  # Less than 100MB
                os.remove(gan_path)
                logger.error("Downloaded wav2lip_gan.pth is too small (likely an error page).")
                raise RuntimeError("Failed to download valid wav2lip_gan.pth")
                
            logger.info("✅ wav2lip_gan.pth downloaded.")

        # Step 4: Download face detection model (s3fd)
        os.makedirs(FACE_DETECTION_DIR, exist_ok=True)
        s3fd_path = os.path.join(FACE_DETECTION_DIR, "s3fd.pth")
        if not os.path.exists(s3fd_path):
            logger.info("Downloading s3fd.pth face detection model...")
            subprocess.run(
                ["wget", "-q", S3FD_URL, "-O", s3fd_path],
                check=True, capture_output=True, text=True,
            )
            logger.info("✅ s3fd.pth downloaded.")

        # Step 5: Patch Wav2Lip for modern Python/NumPy compatibility
        _patch_wav2lip()

        logger.info("✅ Wav2Lip installation complete!")
        return True

    except Exception as e:
        logger.error(f"Wav2Lip installation failed: {e}")
        return False


def _patch_wav2lip():
    """
    Apply compatibility patches for modern Python (3.10+) and NumPy.
    Fixes known issues without modifying core logic.
    """
    # Fix 1: audio.py uses deprecated np.float and scipy imports
    audio_file = os.path.join(WAV2LIP_DIR, "audio.py")
    if os.path.exists(audio_file):
        with open(audio_file, "r", encoding="utf-8") as f:
            content = f.read()

        patched = content
        # Fix scipy signal import
        patched = patched.replace(
            "from scipy.io import wavfile",
            "from scipy.io import wavfile\nimport scipy.signal"
        ) if "import scipy.signal" not in content else patched

        # Fix np.float → float
        patched = patched.replace("np.float", "float")
        # But don't break np.float32, np.float64, etc.
        patched = patched.replace("float32", "np.float32")
        patched = patched.replace("float64", "np.float64")

        # Fix librosa.filters.mel for modern librosa (requires keyword args)
        patched = patched.replace(
            "librosa.filters.mel(hp.sample_rate, hp.n_fft, n_mels=hp.num_mels",
            "librosa.filters.mel(sr=hp.sample_rate, n_fft=hp.n_fft, n_mels=hp.num_mels"
        )

        if patched != content:
            with open(audio_file, "w", encoding="utf-8") as f:
                f.write(patched)
            logger.info("Patched audio.py for NumPy 2.0 compatibility.")

    # Fix 2: Inference.py — multiple compatibility patches
    inference_file = os.path.join(WAV2LIP_DIR, "inference.py")
    if os.path.exists(inference_file):
        with open(inference_file, "r", encoding="utf-8") as f:
            content = f.read()

        patched = content
        # Fix cv2.cv2 reference (removed in modern OpenCV)
        patched = patched.replace("cv2.cv2.ROTATE_90_CLOCKWISE", "cv2.ROTATE_90_CLOCKWISE")

        # Fix torch.load for PyTorch 2.6+ (requires weights_only parameter)
        if "weights_only=False" not in patched:
            patched = patched.replace(
                "torch.load(checkpoint_path)",
                "torch.load(checkpoint_path, weights_only=False)"
            )

        # Fix --static argument: type=bool doesn't work as a flag in argparse
        # Replace type=bool with action='store_true' so --static works without a value
        if "type=bool" in patched and "'--static'" in patched:
            patched = patched.replace(
                "parser.add_argument('--static', type=bool",
                "parser.add_argument('--static', action='store_true'"
            )

        if patched != content:
            with open(inference_file, "w", encoding="utf-8") as f:
                f.write(patched)
            logger.info("Patched inference.py for modern OpenCV + PyTorch 2.6 + static flag.")


def _convert_audio_to_wav(audio_path: Path, temp_dir: Path) -> Path:
    """
    Convert audio to WAV format (16-bit PCM, 16kHz) as required by Wav2Lip.
    Returns path to the WAV file.
    """
    wav_path = temp_dir / "audio_input.wav"
    if wav_path.exists():
        return wav_path

    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-ar", "16000",       # 16kHz sample rate (Wav2Lip's expected rate)
        "-ac", "1",            # Mono
        "-sample_fmt", "s16",  # 16-bit PCM
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Audio conversion failed: {result.stderr}")
        raise RuntimeError("Failed to convert audio to WAV")

    logger.info("Converted audio to WAV format (16kHz, mono).")
    return wav_path


def _add_natural_motion(input_path: Path, output_path: Path) -> None:
    """
    Post-process Wav2Lip output to look like a real human talking.

    Uses FFmpeg crop filter with animated expressions to simulate:
    1. Camera drift — slow sinusoidal X/Y movement (handheld camera feel)
    2. Breathing zoom — rhythmic crop-size variation (~15 breaths/min)
    3. Head bob — subtle vertical movement tied to speech rhythm
    4. Warm color grading + vignette for cinematic look

    All effects use crop-based animation (NOT zoompan, which is image-only).
    """
    logger.info("🎨 Adding natural motion effects to avatar...")

    try:
        # Get video dimensions
        probe = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "default=noprint_wrappers=1:nokey=0",
                str(input_path),
            ],
            capture_output=True, text=True,
        )
        info = {}
        for line in probe.stdout.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                info[k] = v

        w = int(info.get("width", 256))
        h = int(info.get("height", 256))

        # Pre-compute motion parameters as integers
        # We crop to ~90% of frame, giving 5% margin on each side for movement
        base_cw = int(w * 0.90)
        base_ch = int(h * 0.90)
        cx = (w - base_cw) // 2   # center X offset
        cy = (h - base_ch) // 2   # center Y offset

        # Motion amplitudes (in pixels)
        drift_x = int(w * 0.02)     # horizontal camera drift
        drift_y = int(h * 0.015)    # vertical camera drift
        bob_y = int(h * 0.012)      # speech head bob
        nod_y = int(h * 0.005)      # micro nod
        breath = int(w * 0.012)     # breathing zoom (crop size variation)

        # Build FFmpeg expressions as plain strings (avoid f-string brace issues)
        # Crop X position: center + slow drift + tiny jitter
        x_expr = "{cx}+{dx}*sin(t*0.44)+{jx}*sin(t*1.95)".format(
            cx=cx, dx=drift_x, jx=max(drift_x // 4, 1)
        )
        # Crop Y position: center + slow drift + head bob + micro nod
        y_expr = "{cy}+{dy}*sin(t*0.57)+{by}*sin(t*3.14)+{ny}*sin(t*6.91)".format(
            cy=cy, dy=drift_y, by=bob_y, ny=nod_y
        )
        # Crop width/height: base size + breathing variation
        w_expr = "{bw}+{br}*sin(t*1.57)".format(bw=base_cw, br=breath)
        h_expr = "{bh}+{br}*sin(t*1.57)".format(bh=base_ch, br=breath)

        # Assemble filter chain
        filter_chain = (
            # Animated crop: drift + bob + breathing zoom
            "crop='{cw}':'{ch}':'{cx}':'{cy}',"
            # Scale back to original dimensions
            "scale={w}:{h}:flags=lanczos,"
            # Warm color grading for natural skin tones
            "eq=brightness=0.02:saturation=1.08,"
            "colorbalance=rs=0.03:gs=0.01:bs=-0.02:rm=0.02:gm=0.005:bm=-0.01,"
            # Soft vignette for cinematic depth
            "vignette=PI/5"
        ).format(cw=w_expr, ch=h_expr, cx=x_expr, cy=y_expr, w=w, h=h)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", filter_chain,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-an",  # No audio (handled by video_assembler)
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.warning(f"Full motion failed: {result.stderr[-300:]}")
            _add_simple_motion(input_path, output_path, w, h)
        else:
            logger.info("✨ Natural motion effects applied successfully")

    except Exception as e:
        logger.warning(f"Motion post-processing failed: {e}. Using raw output.")
        shutil.copy2(str(input_path), str(output_path))


def _add_simple_motion(input_path: Path, output_path: Path, w: int, h: int) -> None:
    """
    Simplified motion fallback — just breathing zoom + warm colors.
    Used when the full motion filter chain fails.
    """
    logger.info("Using simplified motion effects (fallback)...")

    cw = int(w * 0.94)
    ch = int(h * 0.94)
    ox = int(w * 0.03)
    oy = int(h * 0.03)
    dx = int(w * 0.02)
    dy = int(h * 0.02)

    x_expr = "{ox}+{dx}*sin(t*0.5)".format(ox=ox, dx=dx)
    y_expr = "{oy}+{dy}*sin(t*0.7)".format(oy=oy, dy=dy)

    simple_filter = (
        "crop={cw}:{ch}:'{x}':'{y}',"
        "scale={w}:{h}:flags=lanczos,"
        "eq=brightness=0.02:saturation=1.05"
    ).format(cw=cw, ch=ch, x=x_expr, y=y_expr, w=w, h=h)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", simple_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        logger.warning("Simple motion also failed. Copying raw output.")
        shutil.copy2(str(input_path), str(output_path))
    else:
        logger.info("✨ Simple motion effects applied")


def generate_avatar_video(
    audio_path: Path,
    output_path: Path,
    avatar_img_path: Path = Path("assets/avatar.png"),
) -> bool:
    """
    Generate a lip-synced talking head video using Wav2Lip.

    Uses the wav2lip_gan.pth model for best visual quality.
    The avatar image should be a front-facing portrait photo.

    Args:
        audio_path: Path to TTS audio file (MP3 or WAV).
        output_path: Where to save the generated avatar video.
        avatar_img_path: Path to the avatar face image.

    Returns:
        True if generation succeeded, False otherwise.
    """
    logger.info(f"Generating Wav2Lip avatar video for {audio_path.name}...")

    if not avatar_img_path.exists():
        logger.error(f"Avatar image not found at {avatar_img_path}")
        return False

    if not audio_path.exists():
        logger.error(f"Audio file not found at {audio_path}")
        return False

    # Auto-install Wav2Lip if not present
    if not is_wav2lip_installed():
        logger.info("Wav2Lip not found. Attempting auto-install...")
        if not install_wav2lip():
            logger.error("Wav2Lip installation failed. Cannot generate avatar.")
            return False

    # Always apply compatibility patches before inference
    # (covers cases where Wav2Lip was installed by the notebook cell, not by us)
    _patch_wav2lip()

    # Create temp working directory INSIDE Wav2Lip dir to avoid Google Drive path issues
    temp_dir = Path(WAV2LIP_DIR) / "pipeline_temp"
    os.makedirs(temp_dir, exist_ok=True)
    # Also keep a local temp for audio conversion
    local_temp = output_path.parent / "wav2lip_temp"
    os.makedirs(local_temp, exist_ok=True)

    try:
        # Convert audio to WAV (Wav2Lip requirement)
        wav_path = _convert_audio_to_wav(audio_path, local_temp)

        # Build Wav2Lip inference command
        checkpoint = os.path.join(CHECKPOINTS_DIR, "wav2lip_gan.pth")

        # Save output INSIDE the Wav2Lip directory (avoids Google Drive write issues)
        result_path = str(temp_dir / "wav2lip_result.mp4")

        # Copy avatar image to local temp to avoid Drive path issues
        local_avatar = temp_dir / "avatar_input.png"
        shutil.copy2(str(avatar_img_path.resolve()), str(local_avatar))

        # Copy WAV to local temp too
        local_wav = temp_dir / "audio_input.wav"
        shutil.copy2(str(wav_path), str(local_wav))

        cmd = [
            sys.executable,
            os.path.join(WAV2LIP_DIR, "inference.py"),
            "--checkpoint_path", checkpoint,
            "--face",            str(local_avatar),
            "--audio",           str(local_wav),
            "--outfile",         result_path,
            "--static",
            "--fps",             "30",
            "--pads",            "0", "20", "0", "0",
            "--face_det_batch_size", "4",
            "--wav2lip_batch_size",  "64",
            "--resize_factor",   "1",
            "--nosmooth",
        ]

        logger.info("Running Wav2Lip inference... This takes ~30-60s on a T4 GPU.")
        logger.info(f"  Avatar: {local_avatar}")
        logger.info(f"  Audio:  {local_wav}")
        logger.info(f"  Output: {result_path}")

        # Wav2Lip writes intermediate frames to temp/result.avi — this dir MUST exist
        os.makedirs(os.path.join(WAV2LIP_DIR, "temp"), exist_ok=True)

        result = subprocess.run(
            cmd,
            cwd=WAV2LIP_DIR,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )

        # Always log Wav2Lip output for debugging
        if result.stdout:
            logger.info(f"Wav2Lip stdout:\n{result.stdout[-1500:]}")
        if result.stderr:
            logger.info(f"Wav2Lip stderr:\n{result.stderr[-1500:]}")

        if result.returncode != 0:
            logger.error(f"Wav2Lip inference failed with return code {result.returncode}")
            return False

        # Search multiple possible output locations
        possible_paths = [
            result_path,
            os.path.join(WAV2LIP_DIR, "results", "result_voice.mp4"),
            os.path.join(WAV2LIP_DIR, "results", "wav2lip_result.mp4"),
            str(temp_dir / "result_voice.mp4"),
        ]

        found_path = None
        for p in possible_paths:
            if os.path.exists(p) and os.path.getsize(p) > 1000:
                found_path = p
                logger.info(f"Found Wav2Lip output at: {p}")
                break

        if not found_path:
            # List what IS in the results and temp dirs for debugging
            results_dir = os.path.join(WAV2LIP_DIR, "results")
            if os.path.isdir(results_dir):
                logger.error(f"Files in {results_dir}: {os.listdir(results_dir)}")
            if os.path.isdir(str(temp_dir)):
                logger.error(f"Files in {temp_dir}: {os.listdir(str(temp_dir))}")
            logger.error("Wav2Lip produced no output video at any expected location.")
            return False

        # Copy raw result to a temp file, then post-process for natural motion
        raw_output = temp_dir / "wav2lip_raw.mp4"
        shutil.copy2(found_path, str(raw_output))

        # Apply natural motion effects to make the avatar look alive
        enhanced_output = temp_dir / "wav2lip_enhanced.mp4"
        _add_natural_motion(raw_output, enhanced_output)

        # Use the enhanced version if it succeeded, otherwise fall back to raw
        if enhanced_output.exists() and enhanced_output.stat().st_size > 1000:
            shutil.copy2(str(enhanced_output), output_path)
            logger.info("Applied natural motion post-processing ✅")
        else:
            shutil.copy2(str(raw_output), output_path)
            logger.warning("Motion post-processing failed, using raw Wav2Lip output.")

        # Verify output
        file_size = output_path.stat().st_size
        if file_size < 1000:
            logger.error(f"Output file too small ({file_size} bytes), likely corrupted.")
            return False

        logger.info(
            f"✅ Avatar video generated: {output_path.name} "
            f"({file_size / 1024 / 1024:.1f} MB)"
        )
        return True

    except subprocess.TimeoutExpired:
        logger.error("Wav2Lip timed out after 10 minutes.")
        return False
    except Exception as e:
        logger.error(f"Avatar generation error: {e}", exc_info=True)
        return False
    finally:
        # Cleanup temp files
        shutil.rmtree(str(temp_dir), ignore_errors=True)
        shutil.rmtree(str(local_temp), ignore_errors=True)
        # Also clean Wav2Lip's own temp dir
        wav2lip_temp = os.path.join(WAV2LIP_DIR, "temp")
        if os.path.isdir(wav2lip_temp):
            shutil.rmtree(wav2lip_temp, ignore_errors=True)
