"""
Step 1: Batch Script Generation
Primary: OpenRouter (Free models) with retry logic
Fallback: Google Gemini API (free tier)

Generates 30 days of Tamil YouTube Shorts scripts in a single API call.
"""

import json
import logging
import re                   # FIX 3: moved from inside _parse_response()
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)


def _load_prompt_template() -> str:
    """Load the batch script prompt template."""
    template_path = config.PROMPTS_DIR / "batch_script_prompt.txt"
    return template_path.read_text(encoding="utf-8")


def _get_excluded_topics() -> str:
    """Load previously used topics to avoid repetition."""
    topics_file = config.DATA_DIR / "topics_used.json"
    if topics_file.exists():
        used = json.loads(topics_file.read_text(encoding="utf-8"))
        if used:
            return f"AVOID these previously used topics:\n{json.dumps(used, ensure_ascii=False)}"
    return ""


def _parse_response(response_text: str) -> list[dict]:
    """
    Parse LLM response into a list of script dicts.

    Handles:
    - <think>...</think> reasoning blocks (some models include these)
    - Markdown code fences (```json ... ```)
    - Responses where JSON is embedded in surrounding prose
    """
    text = response_text.strip()

    # Strip <think>...</think> reasoning blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # FIX 4: strip only the opening and closing fence lines, not every ``` line
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)   # remove opening fence
        text = re.sub(r"\n?```\s*$", "", text)           # remove closing fence
        text = text.strip()

    # Locate the outermost JSON array using bracket depth tracking
    start = text.find("[")
    if start == -1:
        raise ValueError(f"No JSON array found in response. Preview: {text[:200]}")

    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        raise ValueError("Unclosed JSON array found in response.")

    data = json.loads(text[start:end])

    if not isinstance(data, list):
        raise ValueError(f"LLM returned {type(data).__name__} instead of a list.")

    valid_data = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            logger.warning("Item at index %d is not a dictionary: %s", i, item)
            continue
        valid_data.append(item)

    if not valid_data:
        raise ValueError(
            "LLM returned a list, but none of the items were valid script objects."
        )

    return valid_data


def _build_prompt() -> str:
    """Build the full prompt from template."""
    template = _load_prompt_template()
    prompt = template.replace("[TOTAL_SCRIPTS]", str(config.TOTAL_DAYS))
    prompt = prompt.replace(
        "[EXCLUDE_TOPICS: List any previously generated topics here so they are not repeated. Leave blank if this is the first batch.]",
        _get_excluded_topics(),
    )
    return prompt


def _try_openrouter(prompt: str, max_retries: int = 3) -> list[dict] | None:
    """Try generating scripts via OpenRouter with retry logic."""
    from openai import OpenAI

    client = OpenAI(
        base_url=config.OPENROUTER_BASE_URL,
        api_key=config.OPENROUTER_API_KEY,
    )

    # FIX 1: removed "Use natural spoken Tanglish" — it directly contradicted
    # the STRICT WRITING RULES in the prompt ("NO Tanglish / STRICT TAMIL").
    # The system message was overriding the user prompt and producing mixed output.
    system_msg = (
        "You are a professional Tamil YouTube script writer and civil engineering expert. "
        "Strictly follow all 'STRICT WRITING RULES' in the user prompt. "
        "Respond only in strict, spoken Tamil — no Tanglish, no English mixing. "
        "Always respond with valid JSON only. No markdown, no explanation."
    )

    models = [
        config.OPENROUTER_MODEL,
        "google/gemini-2.0-flash-exp:free",
        "google/gemini-2.0-flash-lite-preview-02-05:free",
        "deepseek/deepseek-r1:free",
        "minimax/minimax-m2.5:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        config.OPENROUTER_FALLBACK_MODEL,
    ]

    for model in models:
        for attempt in range(1, max_retries + 1):
            try:
                logger.info("Trying %s (attempt %d/%d)...", model, attempt, max_retries)
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.8,
                    max_tokens=8000,
                    extra_headers={
                        "HTTP-Referer": "https://github.com/youtube-shorts-pipeline",
                        "X-Title": "YouTube Shorts Pipeline",
                    },
                )

                raw_text = response.choices[0].message.content
                if not raw_text:
                    raise ValueError(f"Model {model} returned empty content.")

                scripts = _parse_response(raw_text)
                logger.info("Generated %d scripts with %s", len(scripts), model)
                return scripts

            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "rate" in error_str or "limit" in error_str:
                    wait_time = 30 * attempt  # 30s, 60s, 90s
                    logger.warning(
                        "Rate limited on %s. Waiting %ds before retry...",
                        model, wait_time,
                    )
                    time.sleep(wait_time)
                    continue  # FIX 8: explicit continue makes intent unambiguous
                elif "404" in error_str:
                    logger.warning("Model %s not found (404). Skipping.", model)
                    break  # break inner loop → try next model
                else:
                    logger.warning("Model %s failed: %s", model, e)
                    break  # break inner loop → try next model

    return None


def _try_gemini(prompt: str) -> list[dict] | None:
    """Try generating scripts via Google Gemini API (free tier fallback)."""
    if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "your_gemini_api_key_here":
        return None

    try:
        from google import genai
        from google.genai import types  # FIX 6: use typed config object

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        for model_id in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-002"]:
            for attempt in range(1, 3):
                try:
                    logger.info(
                        "Trying Gemini API (%s) attempt %d...", model_id, attempt
                    )
                    # FIX 6: pass a typed GenerateContentConfig, not a raw dict.
                    # Raw dicts are silently ignored in newer SDK versions.
                    response = client.models.generate_content(
                        model=model_id,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.8,
                            max_output_tokens=8000,
                            response_mime_type="application/json",
                        ),
                    )
                    raw_text = response.text
                    if not raw_text:
                        continue

                    scripts = _parse_response(raw_text)
                    logger.info(
                        "Generated %d scripts with Gemini %s", len(scripts), model_id
                    )
                    return scripts

                except Exception as e:
                    error_str = str(e).lower()
                    if "429" in error_str or "resource_exhausted" in error_str:
                        wait_time = 30 * attempt
                        logger.warning(
                            "Gemini %s rate limited. Waiting %ds...", model_id, wait_time
                        )
                        time.sleep(wait_time)
                        continue
                    logger.error("Gemini %s failed: %s", model_id, e)
                    break  # break inner loop → try next model_id

        return None

    except Exception as e:
        logger.warning("Gemini fallback system error: %s", e)
        return None


def generate_scripts(force_regenerate: bool = False) -> list[dict]:
    """
    Generate 30 days of scripts.
    Priority: OpenRouter (free) → Gemini (free tier) fallback.

    Args:
        force_regenerate: If True, regenerate even if cached scripts exist.

    Returns:
        List of script dictionaries, each containing at least 'day', 'title', 'script'.
    """
    # FIX 5: ensure output directories exist before any file writes
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    cache_file = config.DATA_DIR / "scripts_batch.json"

    if cache_file.exists() and not force_regenerate:
        logger.info("Loading cached scripts from %s", cache_file)
        scripts = json.loads(cache_file.read_text(encoding="utf-8"))
        logger.info("Loaded %d cached scripts", len(scripts))
        return scripts

    logger.info("Generating %d scripts...", config.TOTAL_DAYS)

    prompt = _build_prompt()

    # Strategy 1: OpenRouter (free models with retry)
    scripts = _try_openrouter(prompt)

    # Strategy 2: Gemini API (free tier)
    if scripts is None:
        scripts = _try_gemini(prompt)

    if scripts is None:
        raise RuntimeError(
            "All script generation methods failed.\n"
            "This is usually due to rate limiting on free models.\n"
            "Solutions:\n"
            "  1. Wait 1-2 minutes and try again\n"
            "  2. Ensure GEMINI_API_KEY is set in .env\n"
            "  3. Try at a different time (less traffic)"
        )

    if len(scripts) < config.TOTAL_DAYS:
        logger.warning(
            "Only got %d scripts (expected %d).",
            len(scripts), config.TOTAL_DAYS,
        )

    # Normalise and validate each script object
    final_scripts = []
    for s in scripts:
        if not isinstance(s, dict):
            continue

        # Both 'script' and 'title' are mandatory
        if "script" not in s or "title" not in s:
            logger.warning(
                "Skipping incomplete script: %s", s.get("title", "<no title>")
            )
            continue

        # Remap 'id' → 'day' if the model used the new format
        if "id" in s and "day" not in s:
            s["day"] = s["id"]

        # Remap 'topic' → 'topic_category' for internal consistency
        if "topic" in s and "topic_category" not in s:
            s["topic_category"] = s["topic"]

        # Assign a fallback day number if still missing
        if "day" not in s:
            s["day"] = len(final_scripts) + 1

        final_scripts.append(s)

    scripts = final_scripts

    cache_file.write_text(
        json.dumps(scripts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Cached %d valid scripts to %s", len(scripts), cache_file)

    _save_used_topics(scripts)

    return scripts


def _save_used_topics(scripts: list[dict]) -> None:
    """
    Persist topic categories so future batches avoid repeating them.

    FIX 7: wraps the file read in try/except so a corrupt topics file
    does not crash the entire pipeline — it falls back to an empty list.
    """
    topics_file = config.DATA_DIR / "topics_used.json"

    existing: list[str] = []
    if topics_file.exists():
        try:
            existing = json.loads(topics_file.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                logger.warning("topics_used.json is malformed — resetting.")
                existing = []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read topics_used.json (%s) — resetting.", exc)
            existing = []

    new_topics = [
        s.get("topic_category", s.get("title", ""))
        for s in scripts
        if s.get("topic_category") or s.get("title")
    ]
    merged = list(set(existing + new_topics))

    topics_file.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_script_for_day(day: int) -> dict:
    """
    Get the script for a specific day (1-indexed).

    FIX 2: searches by the 'day' field instead of using list index.
    The list index is unreliable after filtering/normalisation in
    generate_scripts() — scripts can be dropped, making index N-1
    map to a different day than N.
    """
    scripts = generate_scripts()
    for s in scripts:
        if s.get("day") == day:
            return s
    raise ValueError(
        f"Day {day} not found in scripts. "
        f"Available days: 1–{len(scripts)}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scripts = generate_scripts()
    print(f"\nGenerated {len(scripts)} scripts")
    print(f"\nDay 1 Preview:")
    print(json.dumps(scripts[0], ensure_ascii=False, indent=2))