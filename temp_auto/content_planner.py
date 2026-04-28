"""
content_planner.py
==================
Generates all 30 civil-engineering YouTube scripts using
the FREE HuggingFace Inference API (Meta Llama 3.1 8B Instruct).
No cost. No credit card. 1 000 req/day on free tier.
"""

import json
import time
import os
import requests
from config import (
    HF_API_TOKEN, HF_SCRIPT_MODEL, HF_FALLBACK_MODEL,
    HF_INFERENCE_URL, SCRIPTS_FILE, DATA_DIR,
    CHANNEL_NAME, TARGET_AUDIENCE
)

# ── 30-day topic plan ─────────────────────────────────────────────────────────
TOPICS = [
    (1,  "Foundation Types Explained",           "Which foundation suits your soil — slab, strip, raft, pile"),
    (2,  "Soil Testing Before Construction",      "Why soil bearing capacity tests prevent cracked slabs"),
    (3,  "Concrete Mix Ratios M15 M20 M25",       "Which mix to use for foundation, columns, and floors"),
    (4,  "How to Read Building Drawings",         "Floor plans, sections, elevations explained simply"),
    (5,  "Brick vs AAC Block vs Hollow Block",    "Cost, strength, thermal comparison for Tamil Nadu"),
    (6,  "Waterproofing Your Foundation",         "Crystalline vs membrane — stop water before it enters"),
    (7,  "Steel Rebar Fe500 vs Fe415 Explained",  "Spacing, cover, and bending basics for homebuilders"),
    (8,  "Roof Types — Which One to Choose",      "RCC slab vs Mangalore tile vs sheet metal"),
    (9,  "Plumbing Rough-In Timing",              "When to lay pipes before casting concrete"),
    (10, "Electrical Conduit in Walls",           "How to embed conduit without weakening structure"),
    (11, "Window and Door Framing Details",       "Chajja, lintel, jamb details that prevent leaks"),
    (12, "Insulation Options for India Climate",  "AAC walls, reflective roof, false ceiling options"),
    (13, "Septic Tank Design and Sizing",         "Correctly size a septic tank for your household"),
    (14, "Damp Proof Course at Plinth Level",     "DPC — what it is and why it protects your walls"),
    (15, "Lintel and Beam Sizing Guide",          "Choose the right beam depth for openings"),
    (16, "Floor Slab Construction Step by Step",  "PCC, reinforcement mat, casting for crack-free floor"),
    (17, "Retaining Wall — When and How",         "Gravity vs cantilever retaining wall for sloped plots"),
    (18, "Site Drainage Planning",                "Slope grading and drains to protect your footings"),
    (19, "Column and Pillar Construction",        "Spacing, sizing, casting columns for two-storey house"),
    (20, "Staircase Design and Dimensions",       "Dog-leg, open-well, straight — riser tread ratio"),
    (21, "Plastering Techniques to Avoid Cracks", "Single vs double coat plaster done right"),
    (22, "Floor Tile Installation Guide",         "Dry lay, adhesive bed, grout — proper sequence"),
    (23, "Roof Waterproofing Methods",            "Brick bat coba, IPS, chemical coating compared"),
    (24, "Compound Wall Construction",            "Footing depth, pillar spacing, coping details"),
    (25, "Gate Post Design That Won't Lean",      "Strong gate foundation and post sizing"),
    (26, "Landscaping for Site Drainage",         "Permeable surfaces and swales to protect building"),
    (27, "10 Common Construction Mistakes",       "Errors that cost homeowners lakhs to fix later"),
    (28, "Building Permit Process in Tamil Nadu", "NOC, approval drawings, completion certificate"),
    (29, "Construction Cost Estimation Guide",    "Rate analysis for brickwork, concrete, finishing"),
    (30, "Final Possession Inspection Checklist", "30 things to verify before taking your new home"),
]

HEADERS = {"Authorization": f"Bearer {HF_API_TOKEN}"}

SYSTEM_PROMPT = f"""You are a senior civil engineer and YouTube educator for homebuilders in Tamil Nadu, India.
Write in warm, confident, natural spoken English — like a trusted engineer friend explaining over tea.
Use real Indian material names, local costs in rupees, and practical Tamil Nadu context.
Format: [HOOK] powerful opening question or fact → [INTRO] 10-second channel intro → [POINTS] 4-5 numbered practical points with visual cues in (parentheses) → [CTA] subscribe + comment call.
Total words: 750-950 (about 6-7 minutes spoken).
At the very end add a section marked ===SHORT=== containing a 55-second standalone script (single most important point).
Write only the script text, no meta-commentary."""

def _hf_generate(prompt: str, model: str) -> str:
    url = f"{HF_INFERENCE_URL}/{model}"
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 1200,
            "temperature": 0.75,
            "top_p": 0.92,
            "repetition_penalty": 1.15,
            "return_full_text": False,
        }
    }
    r = requests.post(url, headers=HEADERS, json=payload, timeout=120)
    if r.status_code == 503:
        # Model loading — wait and retry once
        print(f"    Model loading, waiting 25s...")
        time.sleep(25)
        r = requests.post(url, headers=HEADERS, json=payload, timeout=120)
    r.raise_for_status()
    result = r.json()
    if isinstance(result, list):
        return result[0].get("generated_text", "")
    return result.get("generated_text", "")


def generate_script(day: int, title: str, focus: str) -> dict:
    prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
{SYSTEM_PROMPT}
<|eot_id|><|start_header_id|>user<|end_header_id|>
Write a complete YouTube video script.
Topic: {title}
Focus: {focus}
Target audience: {TARGET_AUDIENCE}
<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""
    # Try primary model, fall back to Mistral
    for model in [HF_SCRIPT_MODEL, HF_FALLBACK_MODEL]:
        try:
            raw = _hf_generate(prompt, model)
            break
        except Exception as e:
            print(f"    Model {model} failed: {e}, trying fallback...")
            raw = ""

    if not raw:
        raw = f"[Script generation failed for Day {day}. Please retry.]"

    # Split main and short
    if "===SHORT===" in raw:
        parts = raw.split("===SHORT===")
        main_script  = parts[0].strip()
        short_script = parts[1].strip() if len(parts) > 1 else ""
    else:
        main_script  = raw.strip()
        short_script = ""

    return {
        "day": day,
        "title": title,
        "focus": focus,
        "main_script": main_script,
        "short_script": short_script,
        "audio_path": None,
        "short_audio_path": None,
        "talking_head_path": None,
        "short_talking_head_path": None,
        "final_video_path": None,
        "final_short_path": None,
        "youtube_url": None,
        "youtube_short_url": None,
        "video_status": "pending",
        "seo": {}
    }


def generate_all_scripts() -> list:
    os.makedirs(DATA_DIR, exist_ok=True)
    scripts = []
    print(f"Generating 30 scripts via HuggingFace (free Llama 3.1)...\n")

    for day, title, focus in TOPICS:
        print(f"  [{day:02d}/30] {title}")
        try:
            s = generate_script(day, title, focus)
            scripts.append(s)
            # Save after each
            with open(SCRIPTS_FILE, "w", encoding="utf-8") as f:
                json.dump(scripts, f, indent=2, ensure_ascii=False)
            print(f"         ✓ saved ({len(s['main_script'])} chars)")
            time.sleep(2)  # be kind to free API rate limits
        except Exception as e:
            print(f"         ✗ FAILED: {e}")
            scripts.append({
                "day": day, "title": title, "focus": focus,
                "main_script": "", "short_script": "", "error": str(e),
                "video_status": "error", "seo": {}
            })

    print(f"\n✓ All scripts saved → {SCRIPTS_FILE}")
    return scripts


def generate_seo(title: str, script_preview: str, day: int) -> dict:
    """Generate SEO metadata using the same free LLM."""
    prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
You are a YouTube SEO expert for Indian civil engineering content. Respond ONLY with valid JSON, no markdown.
<|eot_id|><|start_header_id|>user<|end_header_id|>
Generate SEO metadata for this civil engineering YouTube video.
Title: {title}
Script preview: {script_preview[:250]}
Target: homebuilders in Tamil Nadu, India

Return JSON with keys:
youtube_title (max 70 chars, include power word),
short_title (max 50 chars for Shorts),
description (600 chars, 3 paras, natural keywords),
tags (list of 15 mixed short+longtail),
hashtags (list of 8 starting with #),
thumbnail_text (3-5 words for overlay)
<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""
    try:
        raw = _hf_generate(prompt, HF_SCRIPT_MODEL)
        # Strip markdown fences
        raw = raw.strip().strip("```json").strip("```").strip()
        return json.loads(raw)
    except Exception as e:
        return {
            "youtube_title": title[:70],
            "short_title": title[:50],
            "description": f"Learn about {title} in this practical guide for homebuilders.",
            "tags": ["civil engineering", "construction", "home building", "Tamil Nadu"],
            "hashtags": ["#CivilEngineering", "#Construction", "#HomeBuilding"],
            "thumbnail_text": title[:30]
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_scripts() -> list:
    try:
        with open(SCRIPTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_scripts(scripts: list):
    with open(SCRIPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(scripts, f, indent=2, ensure_ascii=False)

def get_script(day: int) -> dict | None:
    return next((s for s in load_scripts() if s["day"] == day), None)

def update_script(day: int, **kw):
    scripts = load_scripts()
    for s in scripts:
        if s["day"] == day:
            s.update(kw)
    save_scripts(scripts)


if __name__ == "__main__":
    generate_all_scripts()
