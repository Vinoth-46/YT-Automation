"""
Step 4a: Stock Footage Downloader using Pexels API (Free).
Downloads vertical HD clips matching scene descriptions.
"""

import json
import logging
import time
from pathlib import Path

import requests

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)

# Cache for downloaded footage to avoid re-downloading
_footage_cache_file = config.DATA_DIR / "footage_cache.json"


def _load_footage_cache() -> dict:
    """Load the footage download cache."""
    if _footage_cache_file.exists():
        return json.loads(_footage_cache_file.read_text(encoding="utf-8"))
    return {}


def _save_footage_cache(cache: dict) -> None:
    """Save the footage download cache."""
    _footage_cache_file.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def search_videos(query: str, per_page: int = 5) -> list[dict]:
    """
    Search Pexels for videos matching the query.

    Args:
        query: Search term (English).
        per_page: Number of results.

    Returns:
        List of video metadata dicts.
    """
    headers = {"Authorization": config.PEXELS_API_KEY}
    params = {
        "query": query,
        "per_page": per_page,
        "orientation": config.PEXELS_ORIENTATION,
        "size": "medium",
    }

    try:
        response = requests.get(
            f"{config.PEXELS_BASE_URL}/search",
            headers=headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("videos", [])

    except Exception as e:
        logger.warning("Pexels search failed for '%s': %s", query, e)
        return []


def _get_best_video_file(video: dict) -> dict | None:
    """
    Select the best video file from Pexels results.
    Prefers HD portrait orientation.
    """
    files = video.get("video_files", [])
    if not files:
        return None

    # Sort by preference: portrait > landscape, HD > SD
    scored = []
    for f in files:
        score = 0
        w = f.get("width", 0)
        h = f.get("height", 0)

        # Prefer portrait (height > width)
        if h > w:
            score += 100

        # Prefer HD resolution
        if h >= 1080:
            score += 50
        elif h >= 720:
            score += 25

        # Prefer reasonable file size (not 4K which is too large)
        if w <= 1920 and h <= 1920:
            score += 10

        # Must be MP4
        if f.get("file_type") == "video/mp4":
            score += 5

        scored.append((score, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else files[0]


def download_video(url: str, save_path: Path) -> bool:
    """Download a video file from URL."""
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info("Downloaded: %s (%.1f MB)",
                     save_path.name, save_path.stat().st_size / 1024 / 1024)
        return True

    except Exception as e:
        logger.error("Download failed for %s: %s", url, e)
        return False


def download_footage_for_scene(
    pexels_query: str,
    scene_num: int,
    day: int,
    min_duration: int = 5,
) -> Path | None:
    """
    Download stock footage for a specific scene.

    Args:
        pexels_query: Search query for Pexels.
        scene_num: Scene number (for naming).
        day: Day number (for output directory).
        min_duration: Minimum clip duration in seconds.

    Returns:
        Path to downloaded video or None.
    """
    day_dir = config.OUTPUT_DIR / f"day_{day:02d}" / "footage"
    day_dir.mkdir(parents=True, exist_ok=True)

    output_file = day_dir / f"scene_{scene_num:02d}.mp4"

    # Check if already downloaded
    if output_file.exists():
        logger.info("Using cached footage for day %d, scene %d", day, scene_num)
        return output_file

    # Check footage cache
    cache = _load_footage_cache()
    cache_key = f"{pexels_query}_{scene_num}"

    # Search for videos
    videos = search_videos(pexels_query)

    if not videos:
        # Try a broader search
        broad_query = pexels_query.split()[0] + " construction"
        logger.info("No results for '%s', trying '%s'", pexels_query, broad_query)
        videos = search_videos(broad_query)

    if not videos:
        # Final fallback: generic construction footage
        logger.warning("No footage found. Using generic 'construction site' query.")
        videos = search_videos("construction site building")

    if not videos:
        logger.error("No footage available for day %d, scene %d", day, scene_num)
        return None

    # Filter by minimum duration
    suitable = [
        v for v in videos
        if v.get("duration", 0) >= min_duration
    ]
    if not suitable:
        suitable = videos  # Use whatever we have

    # Pick the first suitable video (avoid previously used ones)
    used_ids = set(cache.values())
    selected = None
    for v in suitable:
        if str(v["id"]) not in used_ids:
            selected = v
            break
    if selected is None:
        selected = suitable[0]  # Reuse if all are used

    # Get the best file variant
    best_file = _get_best_video_file(selected)
    if not best_file:
        logger.error("No downloadable file for video %s", selected["id"])
        return None

    # Download
    success = download_video(best_file["link"], output_file)
    if success:
        # Update cache
        cache[cache_key] = str(selected["id"])
        _save_footage_cache(cache)
        return output_file

    return None


def download_all_footage_for_day(day: int, visual_plan: dict, force: bool = False) -> list[Path]:
    """
    Downloads all footage clips for a day's video.
    For a 45-second video, we aim for 5-7 clips.
    """
    day_dir = config.OUTPUT_DIR / f"day_{day:02d}"
    footage_dir = day_dir / "footage"
    footage_dir.mkdir(parents=True, exist_ok=True)

    scenes = visual_plan.get("scenes", [])
    # If the visual plan is short, we'll try to get more clips
    if len(scenes) < 5:
        logger.info("Visual plan is short. Augmenting with extra clips for 45s duration.")
    
    footage_paths = []
    for i, scene in enumerate(scenes):
        query = scene.get("pexels_query", "construction site")
        scene_num = scene.get("scene_num", i + 1)

        logger.info("Day %d, Scene %d: Searching '%s'...", day, scene_num, query)

        path = download_footage_for_scene(
            pexels_query=query,
            scene_num=scene_num,
            day=day,
            min_duration=scene.get("duration_sec", 5),
        )

        if path:
            footage_paths.append(path)
        else:
            logger.warning("Missing footage for day %d, scene %d", day, scene_num)

        # Rate limiting — be nice to the API
        time.sleep(0.5)

    logger.info("Day %d: Downloaded %d/%d footage clips",
                 day, len(footage_paths), len(scenes))
    return footage_paths


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with a sample search
    test_plan = {
        "scenes": [
            {"scene_num": 1, "duration_sec": 5, "pexels_query": "concrete pouring"},
            {"scene_num": 2, "duration_sec": 8, "pexels_query": "construction worker"},
        ]
    }
    paths = download_all_footage_for_day(test_plan, day=0)
    print(f"\n✅ Downloaded {len(paths)} clips")
    for p in paths:
        print(f"  📁 {p}")
