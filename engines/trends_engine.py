"""
TrendsEngine — fetches currently trending civil engineering search terms
from YouTube autocomplete and Google Trends RSS feed.
No API keys required (uses public endpoints).
"""

import asyncio
import logging
import re
import json

logger = logging.getLogger(__name__)

# Seed keywords relevant to the channel
SEED_KEYWORDS = [
    "civil engineering tamil",
    "house construction tips tamil",
    "வீடு கட்டுவது",
    "building construction tamil",
    "concrete tips tamil",
    "foundation construction",
    "brick wall construction",
    "waterproofing house",
    "floor tiling tips",
    "roof construction india",
]

# Google Trends categories
TRENDS_GEO  = "IN"    # India
TRENDS_CAT  = "0"     # All categories


async def fetch_youtube_suggestions(keyword: str, session) -> list[str]:
    """Fetch YouTube search autocomplete suggestions for a keyword."""
    import urllib.parse
    query = urllib.parse.quote(keyword)
    url = (
        f"https://suggestqueries.google.com/complete/search"
        f"?client=youtube&ds=yt&q={query}&hl=ta"
    )
    try:
        async with session.get(url, timeout=8) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
            # Response is JSONP: window.google.ac.h([query, [...]])
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if not match:
                return []
            data = json.loads(match.group())
            # data[1] is the list of suggestions [[term, score], ...]
            suggestions = []
            if len(data) > 1 and isinstance(data[1], list):
                for item in data[1]:
                    if isinstance(item, list) and item:
                        suggestions.append(str(item[0]))
                    elif isinstance(item, str):
                        suggestions.append(item)
            return suggestions[:8]
    except Exception as e:
        logger.debug(f"YouTube suggest failed for '{keyword}': {e}")
        return []


async def fetch_google_trends(session) -> list[str]:
    """Fetch India daily trending searches from Google Trends RSS."""
    url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={TRENDS_GEO}"
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
            titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', text)
            # Filter for construction/engineering related terms
            relevant_terms = []
            keywords = [
                "construction", "building", "house", "floor", "cement",
                "concrete", "foundation", "brick", "roof", "tile",
                "engineer", "civil", "வீடு", "கட்டு", "சிமென்ட்"
            ]
            for title in titles:
                tl = title.lower()
                if any(k in tl for k in keywords):
                    relevant_terms.append(title)
            return relevant_terms[:5]
    except Exception as e:
        logger.debug(f"Google Trends RSS failed: {e}")
        return []


async def get_trending_topics(max_results: int = 10) -> list[str]:
    """
    Main entry point. Returns a ranked list of trending civil engineering
    search terms blending YouTube autocomplete + Google Trends.

    Returns empty list gracefully on any network failure so the pipeline
    can still run without trending data.
    """
    try:
        import aiohttp
        async with aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 (compatible; YTAutoBot/1.0)"}
        ) as session:
            # Fetch suggestions for 3 random seed keywords concurrently
            import random
            seeds = random.sample(SEED_KEYWORDS, min(3, len(SEED_KEYWORDS)))
            tasks = [fetch_youtube_suggestions(seed, session) for seed in seeds]
            tasks.append(fetch_google_trends(session))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_terms = []
            for res in results:
                if isinstance(res, list):
                    all_terms.extend(res)

            # Deduplicate preserving order
            seen = set()
            unique = []
            for t in all_terms:
                tl = t.lower().strip()
                if tl and tl not in seen:
                    seen.add(tl)
                    unique.append(t)

            logger.info(f"TrendsEngine: fetched {len(unique)} trending terms")
            return unique[:max_results]

    except Exception as e:
        logger.warning(f"TrendsEngine failed (non-fatal, pipeline continues): {e}")
        return []
