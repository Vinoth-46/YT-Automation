"""
🎬 YouTube Shorts Pipeline — Main Orchestrator
================================================
Fully automated pipeline for generating and uploading
Tamil Civil Engineering YouTube Shorts.

Usage:
  python main.py --generate-all       Generate all 30 days of content
  python main.py --generate-day 5     Generate content for day 5 only
  python main.py --upload-today       Upload today's scheduled video
  python main.py --upload-day 5       Upload a specific day's video
  python main.py --status             Show pipeline status
  python main.py --validate-day 5     Validate a day's video specs
  python main.py --test-tts           Test TTS with a sample sentence
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

import config
from scripts.script_generator import generate_scripts, get_script_for_day
from scripts.visual_planner import generate_visual_plans, get_visual_plan_for_day
from scripts.tts_generator import generate_tts, get_audio_duration
from scripts.footage_downloader import download_all_footage_for_day
from scripts.subtitle_generator import generate_subtitles
from scripts.avatar_generator import generate_avatar_video
from scripts.video_assembler import assemble_video, validate_video
from scripts.youtube_uploader import (
    upload_today,
    upload_video,
    get_upload_status,
    load_upload_schedule,
    _build_description,
)


def setup_logging():
    """Configure logging to both console and file."""
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = config.LOGS_DIR / f"pipeline_{datetime.now():%Y%m%d}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_file), encoding="utf-8"),
        ],
    )


logger = logging.getLogger("pipeline")


# ── Pipeline Functions ────────────────────────────────

def generate_day(day: int, scripts: list[dict], visual_plans: list[dict],
                 force: bool = False) -> Path:
    """
    Run the full generation pipeline for a single day.

    Steps: Script → Visual Plan → TTS → Footage → Subtitles → Video Assembly

    Returns:
        Path to the final video.
    """
    logger.info("=" * 60)
    logger.info("🎬 GENERATING DAY %d / %d", day, config.TOTAL_DAYS)
    logger.info("=" * 60)

    script = scripts[day - 1]
    visual_plan = visual_plans[day - 1] if day <= len(visual_plans) else None

    if visual_plan is None:
        from scripts.visual_planner import _fallback_plan
        visual_plan = _fallback_plan(script)

    day_dir = config.OUTPUT_DIR / f"day_{day:02d}"
    day_dir.mkdir(parents=True, exist_ok=True)

    # Save script data
    script_file = day_dir / "script.json"
    script_file.write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Save visual plan
    plan_file = day_dir / "visual_plan.json"
    plan_file.write_text(
        json.dumps(visual_plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ── Step 3: Generate TTS Audio ────────────────────
    logger.info("🔊 Step 3: Generating TTS audio...")
    # New format: 'script' contains the full text (including hook + outro)
    script_text = script.get("script", script.get("hook", ""))
    audio_path = generate_tts(script_text, day, force_regenerate=force)
    audio_duration = get_audio_duration(audio_path)
    logger.info("Audio duration: %.1f seconds", audio_duration)

    # ── Step 4a: Download Stock Footage ───────────────
    logger.info("🖼️ Step 4a: Downloading stock footage...")
    footage_paths = download_all_footage_for_day(day, visual_plan, force=force)
    logger.info("Downloaded %d footage clips", len(footage_paths))

    # ── Step 4c: Generate Subtitles ───────────────────
    logger.info("📝 Step 4c: Generating subtitles...")
    timestamps_path = day_dir / "word_timestamps.json"
    subtitle_path = day_dir / "subtitles.ass"

    if timestamps_path.exists():
        from scripts.subtitle_generator import generate_subtitles_from_timestamps
        generate_subtitles_from_timestamps(
            timestamps_path, 
            subtitle_path,
            target_duration=audio_duration
        )
    else:
        subtitle_path = generate_subtitles(
            day=day,
            script_text=script_text,
            audio_duration=audio_duration,
            force_regenerate=force,
        )

    # ── Step 4d: Generate Talking Head Avatar ─────────
    is_footage_only = getattr(config, "VIDEO_MODE", "avatar") == "footage_only"
    avatar_video_path = config.OUTPUT_DIR / f"day_{day:02d}" / "avatar_video.mp4"
    
    if is_footage_only:
        logger.info("🎬 Mode is footage_only. Skipping avatar generation.")
        avatar_video_path = None
    else:
        logger.info("👤 Step 4d: Generating Avatar Talking Head...")
        if force or not avatar_video_path.exists():
            success = generate_avatar_video(audio_path, avatar_video_path)
            if not success:
                logger.warning("Avatar generation failed. Proceeding without avatar.")
                avatar_video_path = None
        else:
            logger.info("Using cached avatar video for day %d", day)

    # ── Step 4b: Assemble Video ───────────────────────
    logger.info("🎥 Step 4b: Assembling final video...")
    from scripts.telegram_bot import bot
    bot.log_to_telegram(f"🎥 Assembling Video for Day {day}...")
    
    final_video_path = assemble_video(
        day=day,
        visual_plan=visual_plan,
        audio_path=audio_path,
        subtitle_path=subtitle_path,
        footage_paths=footage_paths,
        avatar_path=avatar_video_path,
        force_regenerate=force,
    )

    if final_video_path:
        logger.info("✅ Pipeline complete for day %d: %s", day, final_video_path)
        
        # ── Step 4e: SEO Optimization ─────────────────────
        logger.info("📈 Step 4e: Optimizing SEO...")
        from scripts.seo_expert import optimize_seo
        seo_data = optimize_seo(script_text, script.get("topic", ""))
        logger.info("Generated hashtags: %s", ", ".join(seo_data['hashtags']))

        # In production, this is where we would call upload_video()
        bot.notify_video_ready(day)
        
        if day == 30:
            bot.ask_for_renewal(1) # Assuming Month 1
    else:
        logger.error("❌ Pipeline failed for day %d", day)
        bot.send_message(f"❌ *Error:* Day {day} assembly failed. Check logs.")

    # ── Validate ──────────────────────────────────────
    video_path = final_video_path
    validation = validate_video(video_path)
    logger.info("✅ Video validation: %s", "PASSED" if validation["is_valid"] else "FAILED")
    logger.info("   Resolution: %dx%d", validation["width"], validation["height"])
    logger.info("   Duration: %.1f sec", validation["duration_sec"])
    logger.info("   Size: %.1f MB", validation["file_size_mb"])

    return video_path


def generate_all(force: bool = False):
    """Generate content for all 30 days."""
    logger.info("🚀 Starting FULL pipeline for %d days...", config.TOTAL_DAYS)
    start_time = datetime.now()

    # ── Step 1: Batch Generate Scripts ────────────────
    logger.info("📝 Step 1: Generating %d scripts...", config.TOTAL_DAYS)
    scripts = generate_scripts(force_regenerate=force)
    logger.info("✅ Got %d scripts", len(scripts))

    # ── Step 2: Batch Generate Visual Plans ───────────
    logger.info("🎬 Step 2: Generating visual plans...")
    visual_plans = generate_visual_plans(scripts, force_regenerate=force)
    logger.info("✅ Got %d visual plans", len(visual_plans))

    # ── Steps 3-4: Generate Each Day ──────────────────
    results = []
    for day in range(1, min(len(scripts), config.TOTAL_DAYS) + 1):
        try:
            video_path = generate_day(day, scripts, visual_plans, force=force)
            results.append({"day": day, "status": "success", "path": str(video_path)})
        except Exception as e:
            logger.error("❌ Day %d failed: %s", day, e, exc_info=True)
            results.append({"day": day, "status": "failed", "error": str(e)})

    # ── Summary ───────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()
    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")

    logger.info("=" * 60)
    logger.info("📊 PIPELINE COMPLETE")
    logger.info("   Total time: %.1f minutes", elapsed / 60)
    logger.info("   Success: %d / %d", success, len(results))
    logger.info("   Failed: %d / %d", failed, len(results))
    logger.info("=" * 60)

    # Save results
    results_file = config.DATA_DIR / "generation_results.json"
    results_file.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Initialize upload schedule
    load_upload_schedule()
    logger.info("📅 Upload schedule created. Run --upload-today daily to upload.")


def show_status():
    """Show current pipeline status."""
    print("\n" + "=" * 60)
    print("📊 YOUTUBE SHORTS PIPELINE STATUS")
    print("=" * 60)

    # Check scripts
    scripts_file = config.DATA_DIR / "scripts_batch.json"
    if scripts_file.exists():
        scripts = json.loads(scripts_file.read_text(encoding="utf-8"))
        print(f"\n📝 Scripts: {len(scripts)} generated ✅")
    else:
        print("\n📝 Scripts: Not generated ❌")

    # Check visual plans
    plans_file = config.DATA_DIR / "visual_plans.json"
    if plans_file.exists():
        plans = json.loads(plans_file.read_text(encoding="utf-8"))
        print(f"🎬 Visual Plans: {len(plans)} generated ✅")
    else:
        print("🎬 Visual Plans: Not generated ❌")

    # Check generated videos
    generated = 0
    for day in range(1, config.TOTAL_DAYS + 1):
        video = config.OUTPUT_DIR / f"day_{day:02d}" / "final_video.mp4"
        if video.exists():
            generated += 1
    print(f"🎥 Videos: {generated}/{config.TOTAL_DAYS} generated")

    # Check upload status
    schedule_file = config.DATA_DIR / "upload_schedule.json"
    if schedule_file.exists():
        status = get_upload_status()
        print(f"\n📤 Upload Status:")
        print(f"   Pending:  {status.get('pending', 0)}")
        print(f"   Uploaded: {status.get('uploaded', 0)}")
        print(f"   Failed:   {status.get('failed', 0)}")
    else:
        print("\n📤 Upload Schedule: Not created")

    # Check API keys
    print(f"\n🔑 API Keys:")
    print(f"   OpenRouter: {'✅ Set' if config.OPENROUTER_API_KEY and 'your_' not in config.OPENROUTER_API_KEY else '❌ Not set'}")
    print(f"   Pexels:     {'✅ Set' if config.PEXELS_API_KEY and 'your_' not in config.PEXELS_API_KEY else '❌ Not set'}")
    print(f"   Gemini:     {'✅ Set' if config.GEMINI_API_KEY and 'your_' not in config.GEMINI_API_KEY else '❌ Not set'}")

    # Check system dependencies
    print(f"\n🔧 System Dependencies:")
    _check_dependency("ffmpeg", "ffmpeg -version")
    _check_dependency("ffprobe", "ffprobe -version")

    print("\n" + "=" * 60)


def _check_dependency(name: str, cmd: str):
    """Check if a system dependency is available."""
    import subprocess
    try:
        subprocess.run(cmd.split(), capture_output=True, check=True)
        print(f"   {name}: ✅ Available")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"   {name}: ❌ Not found (install required)")


def test_tts():
    """Test TTS with a sample Tamil sentence."""
    logger.info("🔊 Testing TTS...")
    test_text = (
        "வணக்கம் நண்பர்களே! இன்று ஒரு முக்கியமான "
        "civil engineering tip பார்க்கலாம். "
        "Concrete mix-ல water-cement ratio மிக முக்கியம்."
    )
    audio = generate_tts(test_text, day=0, force_regenerate=True)
    duration = get_audio_duration(audio)
    logger.info("✅ TTS test passed! Audio: %s (%.1fs)", audio, duration)


# ── CLI Entry Point ───────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🎬 YouTube Shorts Pipeline — Tamil Civil Engineering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --generate-all       Generate all 30 days
  python main.py --generate-day 1     Generate day 1 only
  python main.py --upload-today       Upload today's video
  python main.py --status             Show pipeline status
  python main.py --test-tts           Test TTS audio generation
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--telegram-bot", action="store_true",
                        help="Start the interactive Telegram Production Bot")
    group.add_argument("--generate-all", action="store_true",
                        help="Generate content for all 30 days")
    group.add_argument("--generate-day", type=int, metavar="N",
                        help="Generate content for day N only")
    group.add_argument("--upload-today", action="store_true",
                        help="Upload today's scheduled video")
    group.add_argument("--upload-day", type=int, metavar="N",
                        help="Upload video for day N")
    group.add_argument("--generate-today", action="store_true",
                        help="Generate content for today's scheduled day")
    group.add_argument("--status", action="store_true",
                        help="Show pipeline status")
    group.add_argument("--validate-day", type=int, metavar="N",
                        help="Validate video for day N")
    group.add_argument("--test-tts", action="store_true",
                        help="Test TTS with sample Tamil text")

    parser.add_argument("--force", action="store_true",
                         help="Force regeneration (ignore cache)")
    parser.add_argument("--start-date", type=str, metavar="YYYY-MM-DD",
                         help="Project start date for --generate-today (default: today)")

    args = parser.parse_args()

    setup_logging()

    if args.telegram_bot:
        from scripts.telegram_bot import main as start_bot
        start_bot()
        return

    if args.status:
        show_status()
        return

    if args.test_tts:
        test_tts()
        return

    if args.generate_all:
        generate_all(force=args.force)
        return

    if args.generate_day or args.generate_today:
        day = args.generate_day
        if args.generate_today:
            # Load start date from a hidden file or use current day as Day 1
            start_date_file = Path(".start_date")
            if args.start_date:
                start_dt = datetime.strptime(args.start_date, "%Y-%m-%d")
                start_date_file.write_text(args.start_date)
            elif start_date_file.exists():
                start_dt = datetime.strptime(start_date_file.read_text().strip(), "%Y-%m-%d")
            else:
                start_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                start_date_file.write_text(start_dt.strftime("%Y-%m-%d"))
            
            delta = datetime.now() - start_dt
            day = delta.days + 1
            
            if day > config.TOTAL_DAYS:
                print(f"✅ Challenge completed! (Today is day {day}, but only 30 days defined).")
                return
            
            logger.info("📅 Today is scheduled as Day %d", day)

        scripts = generate_scripts()
        visual_plans = generate_visual_plans(scripts)
        generate_day(day, scripts, visual_plans, force=args.force)
        return

    if args.upload_today:
        scripts = generate_scripts()
        result = upload_today(scripts)
        if result:
            print(f"\n✅ Uploaded: {result['url']}")
        else:
            print("\n📭 No videos to upload today.")
        return

    if args.upload_day:
        scripts = generate_scripts()
        day = args.upload_day
        script = scripts[day - 1] if day <= len(scripts) else {}

        video_path = config.OUTPUT_DIR / f"day_{day:02d}" / "final_video.mp4"
        if not video_path.exists():
            print(f"❌ Video not found for day {day}. Run --generate-day {day} first.")
            return

        result = upload_video(
            video_path=video_path,
            title=script.get("title", f"Civil Engineering Tip #{day} #Shorts"),
            description=_build_description(script),
            tags=script.get("keywords", []) + ["Shorts", "CivilEngineering", "Tamil"],
        )
        print(f"\n✅ Uploaded: {result['url']}")
        return

    if args.validate_day:
        video_path = config.OUTPUT_DIR / f"day_{args.validate_day:02d}" / "final_video.mp4"
        if not video_path.exists():
            print(f"❌ Video not found for day {args.validate_day}")
            return

        v = validate_video(video_path)
        print(f"\n📋 Validation Results for Day {args.validate_day}:")
        print(f"   Resolution: {v['width']}x{v['height']}")
        print(f"   Duration:   {v['duration_sec']:.1f}s")
        print(f"   Size:       {v['file_size_mb']:.1f} MB")
        print(f"   Codec:      {v['codec']}")
        print(f"   Vertical:   {'✅' if v['is_vertical'] else '❌'}")
        print(f"   <60 sec:    {'✅' if v['is_shorts_length'] else '❌'}")
        print(f"   Overall:    {'✅ VALID' if v['is_valid'] else '❌ INVALID'}")


if __name__ == "__main__":
    main()
