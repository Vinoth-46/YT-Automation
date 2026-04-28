"""
Step 6: SEO Expert — Hashtag & Description Optimizer
Generates high-reach hashtags and descriptions for YouTube Shorts.
"""

import json
import logging
from openai import OpenAI
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)

def _get_client() -> OpenAI:
    return OpenAI(
        base_url=config.OPENROUTER_BASE_URL,
        api_key=config.OPENROUTER_API_KEY,
    )

def optimize_seo(script_text: str, topic: str) -> dict:
    """
    Uses AI to generate the best hashtags and description for the video.
    """
    client = _get_client()
    
    prompt = f"""
    Analyze this Tamil civil engineering script and generate:
    1. A catchy YouTube Shorts title in Tamil (under 60 chars).
    2. 5-7 trending hashtags (mix of English and Tamil).
    3. A brief description that includes a call to action for 'Kitcha Enterprises'.

    SCRIPT: {script_text}
    TOPIC: {topic}

    Respond ONLY in JSON format:
    {{
        "seo_title": "...",
        "hashtags": ["#tag1", "#tag2", ...],
        "description": "..."
    }}
    """

    try:
        response = client.chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500
        )
        
        raw_text = response.choices[0].message.content
        # Extract JSON
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        return json.loads(raw_text[start:end])
    except Exception as e:
        logger.error(f"SEO Optimization failed: {e}")
        # Fallback
        return {
            "seo_title": f"{topic} Tips in Tamil",
            "hashtags": ["#CivilEngineering", "#TamilShorts", "#ConstructionTips", "#KitchaEnterprises"],
            "description": "Follow Kitcha Enterprises for more civil engineering content!"
        }

if __name__ == "__main__":
    # Test
    res = optimize_seo("காங்கிரீட் போடும்போது கவனிக்க வேண்டியவை", "Concrete Pouring")
    print(json.dumps(res, indent=2))
