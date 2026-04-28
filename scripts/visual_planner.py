"""
Step 2: Visual Planning — Scene breakdowns, captions, and animation directives.
Batches 10 scripts per API call (3 calls total for 30 scripts).
"""

import json
import logging
from pathlib import Path
from openai import OpenAI

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)


def _get_client() -> OpenAI:
    """Create OpenRouter client."""
    return OpenAI(
        base_url=config.OPENROUTER_BASE_URL,
        api_key=config.OPENROUTER_API_KEY,
    )


def _load_prompt_template() -> str:
    """Load the visual plan prompt template."""
    template_path = config.PROMPTS_DIR / "visual_plan_prompt.txt"
    return template_path.read_text(encoding="utf-8")


def _parse_response(response_text: str) -> list[dict]:
    """Parse LLM response into list of visual plans with validation."""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        logger.error("Raw response: %s", response_text)
        raise ValueError("No JSON array found in visual plan response")

    try:
        plans = json.loads(text[start:end])
        if not isinstance(plans, list):
            plans = [plans]
            
        # Validation: Ensure each plan has 'day' and 'scenes'
        valid_plans = []
        for p in plans:
            if isinstance(p, dict) and "scenes" in p:
                if not p["scenes"]:
                     logger.warning("Plan for day %s has empty scenes. Skipping.", p.get("day"))
                     continue
                valid_plans.append(p)
            else:
                logger.warning("Invalid plan format: %s", p)
        
        if not valid_plans:
            raise ValueError("No valid visual plans found in response")
            
        return valid_plans

    except json.JSONDecodeError as e:
        logger.error("JSON decode error: %s", e)
        logger.error("Cleaned text: %s", text[start:end])
        raise


def generate_visual_plans(
    scripts: list[dict],
    force_regenerate: bool = False,
) -> list[dict]:
    """
    Generate visual plans for all scripts, batched.

    Args:
        scripts: List of script dicts from Step 1.
        force_regenerate: If True, regenerate even if cached.

    Returns:
        List of visual plan dicts (one per script).
    """
    cache_file = config.DATA_DIR / "visual_plans.json"

    if cache_file.exists() and not force_regenerate:
        logger.info("Loading cached visual plans from %s", cache_file)
        plans = json.loads(cache_file.read_text(encoding="utf-8"))
        logger.info("Loaded %d cached visual plans", len(plans))
        return plans

    logger.info("Generating visual plans for %d scripts...", len(scripts))

    client = _get_client()
    prompt_template = _load_prompt_template()
    all_plans = []

    # Process in batches
    batch_size = config.VISUAL_PLAN_BATCH_SIZE
    for i in range(0, len(scripts), batch_size):
        batch = scripts[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(scripts) + batch_size - 1) // batch_size

        logger.info("Processing visual plan batch %d/%d (%d scripts)...",
                     batch_num, total_batches, len(batch))

        # Prepare minimal script info for the prompt (token optimization)
        minimal_scripts = [
            {
                "day": s.get("day", s.get("id", i + 1)),
                "title": s.get("title", ""),
                "script": s.get("script", ""),
                "hook": s.get("hook", ""),
                "bg_suggestion": s.get("bg_suggestion", ""),
            }
            for i, s in enumerate(batch)
        ]

        prompt = prompt_template.replace(
            "[Paste your scripts JSON array here. Each object must include: id, topic, hook, script, duration_sec]",
            json.dumps(minimal_scripts, ensure_ascii=False)
        )

        models_to_try = [config.OPENROUTER_MODEL, config.OPENROUTER_FALLBACK_MODEL]
        batch_plans = None

        for model in models_to_try:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a professional video director for YouTube Shorts. "
                                "Plan stock footage for the BOTTOM HALF of a split-screen layout. "
                                "The top half shows a talking-head avatar (already handled). "
                                "Always respond with valid JSON only."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=6000,
                    extra_headers={
                        "HTTP-Referer": "https://github.com/youtube-shorts-pipeline",
                        "X-Title": "YouTube Shorts Pipeline",
                    },
                )

                raw_text = response.choices[0].message.content
                batch_plans = _parse_response(raw_text)
                logger.info("Batch %d: generated %d visual plans with %s",
                            batch_num, len(batch_plans), model)
                break

            except Exception as e:
                logger.warning("Model %s failed for batch %d: %s",
                               model, batch_num, e)
                continue

        if batch_plans is None:
            # Generate fallback plans
            logger.warning("All models failed for batch %d. Using fallback plans.",
                           batch_num)
            batch_plans = [_fallback_plan(s) for s in batch]

        all_plans.extend(batch_plans)

    # Cache results
    cache_file.write_text(
        json.dumps(all_plans, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Cached %d visual plans to %s", len(all_plans), cache_file)

    return all_plans


def _fallback_plan(script: dict) -> dict:
    """Generate a basic fallback visual plan if API fails (approx 45s)."""
    bg = script.get("bg_suggestion", "construction site aerial view")
    day_num = script.get("day", script.get("id", 1))
    return {
        "day": day_num,
        "scenes": [
            {"scene_num": 1, "duration_sec": 7, "description": "Hook", "pexels_query": "construction site worker", "animation": "zoom_in"},
            {"scene_num": 2, "duration_sec": 8, "description": "Body 1", "pexels_query": "civil engineering work", "animation": "pan_left"},
            {"scene_num": 3, "duration_sec": 8, "description": "Body 2", "pexels_query": "concrete pouring", "animation": "static"},
            {"scene_num": 4, "duration_sec": 7, "description": "Body 3", "pexels_query": "building foundation", "animation": "zoom_out"},
            {"scene_num": 5, "duration_sec": 8, "description": "Body 4", "pexels_query": "architectural site", "animation": "pan_right"},
            {"scene_num": 6, "duration_sec": 7, "description": "Outro", "pexels_query": "modern apartment building", "animation": "fade_in"},
        ],
    }


def get_visual_plan_for_day(day: int, scripts: list[dict]) -> dict:
    """Get visual plan for a specific day."""
    plans = generate_visual_plans(scripts)
    for plan in plans:
        if plan.get("day") == day:
            return plan
    # Fallback to index-based lookup
    if day - 1 < len(plans):
        return plans[day - 1]
    raise ValueError(f"No visual plan found for day {day}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from script_generator import generate_scripts

    scripts = generate_scripts()
    plans = generate_visual_plans(scripts)
    print(f"\n✅ Generated {len(plans)} visual plans")
    print(f"\n🎬 Day 1 Preview:")
    print(json.dumps(plans[0], ensure_ascii=False, indent=2))
