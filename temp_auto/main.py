"""
main.py — Civil Build TV  |  100% Free Automation Stack
=========================================================

Usage
-----
  python main.py --init          # generate all 30 scripts once
  python main.py --start         # start the scheduler (keep running 24/7)
  python main.py --run DAY       # manually run full pipeline for a day
  python main.py --status        # print current progress table
  python main.py --auth-youtube  # one-time YouTube OAuth2 browser login

Full pipeline per day
---------------------
  [00:00 IST] Generate audio + talking-head + captions for TOMORROW
  [10:00 IST] Compose + upload + publish TODAY's video → Telegram alert
"""

import os
import sys
import json
import argparse
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    DATA_DIR, PROGRESS_FILE, PUBLISH_HOUR_IST, PUBLISH_MINUTE_IST,
    SHORTS_MAX_SECONDS, CHANNEL_NAME
)
from content_planner import (
    generate_all_scripts, generate_seo,
    load_scripts, get_script, update_script
)
from voice_generator import generate_voice
from talking_head import generate_talking_head, trim_to_duration
from caption_generator import generate_captions
from video_composer import compose_all, download_background
from youtube_uploader import (
    upload_video, notify_published, notify_generating,
    notify_error, notify_start, youtube_auth_once
)

IST = timezone(timedelta(hours=5, minutes=30))

# ── Progress helpers ──────────────────────────────────────────────────────────

def _load_progress() -> dict:
    try:
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"start_date": None, "completed": []}

def _save_progress(p: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(p, f, indent=2)

def _today_day() -> int:
    p = _load_progress()
    if not p.get("start_date"):
        return 1
    start = date.fromisoformat(p["start_date"])
    return max(1, min((date.today() - start).days + 1, 30))


# ── Core pipeline ─────────────────────────────────────────────────────────────

def run_generation(day: int):
    """
    Generate everything for `day` so it's ready to publish the next morning.
    Steps: voice → talking head (main+short) → captions (main+short).
    """
    script = get_script(day)
    if not script:
        print(f"No script for Day {day}. Run --init first.")
        return

    title  = script["title"]
    main_s = script["main_script"]
    short_s = script.get("short_script") or main_s[:600]

    print(f"\n{'═'*60}")
    print(f" GENERATION — Day {day}: {title}")
    print(f"{'═'*60}")
    notify_generating(day, title)

    try:
        # ── 1. Voice (XTTS v2 — English + Tamil intro) ───────────────
        print("\n[1/4] Voice synthesis (XTTS v2)...")
        audio_path       = generate_voice(main_s,  title, day, is_short=False)
        short_audio_path = generate_voice(short_s, title, day, is_short=True)

        # ── 2. Talking-head (SadTalker) ──────────────────────────────
        print("\n[2/4] Talking-head (SadTalker)...")
        th_path  = generate_talking_head(audio_path, day, is_short=False)
        sth_path = generate_talking_head(short_audio_path, day, is_short=True)

        # Trim Short talking-head to SHORTS_MAX_SECONDS
        from config import SHORTS_DIR
        short_th_trimmed = os.path.join(SHORTS_DIR, f"day_{day:02d}_th_trimmed.mp4")
        trim_to_duration(sth_path, short_th_trimmed, SHORTS_MAX_SECONDS)

        # ── 3. Captions (Whisper → IndicTrans2 → ASS) ────────────────
        print("\n[3/4] Dual-language captions (Whisper + IndicTrans2)...")
        ass_path       = generate_captions(audio_path,       day, is_short=False)
        short_ass_path = generate_captions(short_audio_path, day, is_short=True)

        # ── 4. SEO metadata ───────────────────────────────────────────
        print("\n[4/4] SEO metadata (Llama 3.1)...")
        seo = generate_seo(title, main_s, day)

        update_script(day,
            audio_path=audio_path,
            short_audio_path=short_audio_path,
            talking_head_path=th_path,
            short_talking_head_path=short_th_trimmed,
            ass_path=ass_path,
            short_ass_path=short_ass_path,
            seo=seo,
            video_status="assets_ready"
        )
        print(f"\n✓ Day {day} assets ready for publish tomorrow.")

    except Exception as e:
        print(f"\n✗ Generation FAILED Day {day}: {e}")
        update_script(day, video_status="error", error=str(e))
        notify_error(day, "generation", str(e))
        raise


def run_publish(day: int):
    """
    Compose + upload + publish the pre-generated assets for `day`.
    """
    script = get_script(day)
    if not script or script.get("video_status") != "assets_ready":
        msg = f"Day {day} assets not ready (status={script.get('video_status') if script else 'missing'})"
        print(f"\n✗ {msg}")
        notify_error(day, "publish", msg)
        return

    title  = script["title"]
    seo    = script.get("seo", {})

    print(f"\n{'═'*60}")
    print(f" PUBLISH — Day {day}: {title}")
    print(f"{'═'*60}")

    try:
        # ── Compose videos ────────────────────────────────────────────
        print("\n[1/2] Composing final videos (FFmpeg)...")
        main_path, short_path = compose_all(
            talking_head_path  = script["talking_head_path"],
            short_head_path    = script["short_talking_head_path"],
            audio_path         = script["audio_path"],
            short_audio_path   = script["short_audio_path"],
            ass_path           = script["ass_path"],
            short_ass_path     = script["short_ass_path"],
            day                = day,
            title              = title,
        )

        # ── Build description ─────────────────────────────────────────
        description = _build_description(seo, title)
        yt_title    = seo.get("youtube_title", title)[:100]
        tags        = seo.get("tags", ["civil engineering", "construction", "home building"])

        # ── Upload main video ─────────────────────────────────────────
        print("\n[2/2] Uploading to YouTube...")
        yt_url = upload_video(
            video_path  = main_path,
            title       = yt_title,
            description = description,
            tags        = tags,
            is_short    = False,
            publish_now = True,
        )

        # ── Upload Short ──────────────────────────────────────────────
        short_url = None
        if os.path.exists(short_path):
            short_url = upload_video(
                video_path  = short_path,
                title       = seo.get("short_title", title)[:95],
                description = description,
                tags        = tags,
                is_short    = True,
                publish_now = True,
            )

        # ── Update status & notify ────────────────────────────────────
        update_script(day,
            final_video_path  = main_path,
            final_short_path  = short_path,
            youtube_url       = yt_url,
            youtube_short_url = short_url,
            video_status      = "published"
        )
        notify_published(day, title, yt_url, short_url)

        p = _load_progress()
        if day not in p.get("completed", []):
            p.setdefault("completed", []).append(day)
            _save_progress(p)

        print(f"\n✓ Day {day} PUBLISHED!")
        print(f"  Main:  {yt_url}")
        if short_url:
            print(f"  Short: {short_url}")

    except Exception as e:
        print(f"\n✗ Publish FAILED Day {day}: {e}")
        update_script(day, video_status="publish_error", error=str(e))
        notify_error(day, "publish", str(e))
        raise


def _build_description(seo: dict, title: str) -> str:
    base = seo.get("description", f"Learn about {title} in this practical guide for homebuilders in Tamil Nadu.")
    hashtags = " ".join(seo.get("hashtags", ["#CivilEngineering", "#Construction"]))
    return (
        f"{base}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Subscribe to {CHANNEL_NAME} for daily civil engineering tips.\n"
        f"🔔 Turn on notifications — new video every day at 10 AM IST!\n\n"
        f"Captions available in English and Tamil 🇮🇳\n\n"
        f"⚠️ Always consult a licensed structural engineer for your project.\n\n"
        f"{hashtags}"
    )


# ── Scheduled jobs ────────────────────────────────────────────────────────────

def _job_generate():
    """Midnight IST — generate TOMORROW's video."""
    tomorrow = _today_day() + 1
    if tomorrow > 30:
        print("All 30 days complete! 🎉")
        return
    print(f"\n[SCHEDULER midnight] Generating Day {tomorrow}...")
    run_generation(tomorrow)


def _job_publish():
    """10:00 AM IST — publish TODAY's video."""
    today = _today_day()
    if today > 30:
        print("All 30 days complete! 🎉")
        return
    print(f"\n[SCHEDULER 10AM] Publishing Day {today}...")
    run_publish(today)


# ── CLI ───────────────────────────────────────────────────────────────────────

def cmd_init():
    os.makedirs(DATA_DIR, exist_ok=True)
    p = {"start_date": date.today().isoformat(), "completed": []}
    _save_progress(p)
    generate_all_scripts()
    print("\nPre-generating Day 1 assets (for tomorrow's first publish)...")
    run_generation(1)
    notify_start()
    print(f"\n✓ INIT COMPLETE. First publish: tomorrow at {PUBLISH_HOUR_IST:02d}:00 AM IST")
    print("  Run: python main.py --start")


def cmd_start():
    p = _load_progress()
    if not p.get("start_date"):
        print("Not initialized. Run: python main.py --init")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(_job_generate, CronTrigger(hour=0,  minute=0,  timezone="Asia/Kolkata"), id="gen")
    scheduler.add_job(_job_publish,  CronTrigger(hour=PUBLISH_HOUR_IST, minute=PUBLISH_MINUTE_IST, timezone="Asia/Kolkata"), id="pub")

    notify_start()
    print(f"\n{CHANNEL_NAME} scheduler running.")
    print(f"  Midnight: generate next day's video")
    print(f"  {PUBLISH_HOUR_IST:02d}:{PUBLISH_MINUTE_IST:02d}: publish + Telegram alert")
    print("  Ctrl+C to stop\n")
    scheduler.start()


def cmd_status():
    scripts  = load_scripts()
    progress = _load_progress()
    print(f"\n{'═'*65}")
    print(f"  {CHANNEL_NAME} — Pipeline Status")
    print(f"{'═'*65}")
    print(f"  Start: {progress.get('start_date', 'not initialized')}   Done: {len(progress.get('completed',[]))}/30\n")
    icons = {"published": "✅", "assets_ready": "⏳", "error": "❌", "publish_error": "❌", "pending": "⬜"}
    for s in scripts:
        icon = icons.get(s.get("video_status", "pending"), "⬜")
        print(f"  Day {s['day']:02d} {icon}  {s['title'][:50]:50}  [{s.get('video_status','pending')}]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Civil Build TV — Free YouTube Automation")
    ap.add_argument("--init",          action="store_true", help="Generate all 30 scripts + Day 1 assets")
    ap.add_argument("--start",         action="store_true", help="Start daily scheduler")
    ap.add_argument("--run",           type=int, metavar="DAY", help="Manually run full pipeline for a day")
    ap.add_argument("--generate",      type=int, metavar="DAY", help="Generate assets only for a day")
    ap.add_argument("--publish",       type=int, metavar="DAY", help="Publish pre-generated day")
    ap.add_argument("--status",        action="store_true", help="Show progress table")
    ap.add_argument("--auth-youtube",  action="store_true", help="One-time YouTube OAuth2 login")
    args = ap.parse_args()

    if args.init:         cmd_init()
    elif args.start:      cmd_start()
    elif args.run:        run_generation(args.run); run_publish(args.run)
    elif args.generate:   run_generation(args.generate)
    elif args.publish:    run_publish(args.publish)
    elif args.status:     cmd_status()
    elif args.auth_youtube: youtube_auth_once()
    else:                 ap.print_help()
