"""
TrendsEngine — fetches currently trending civil engineering search terms
from YouTube autocomplete, Google Trends RSS, and YouTube Shorts trending tags.
No API keys required (uses public endpoints).

Enhanced: Fetches daily trending hashtags for maximum YouTube Shorts discovery.
"""

import asyncio
import logging
import re
import json
from datetime import datetime

logger = logging.getLogger(__name__)

# Seed keywords relevant to the channel — expanded for broader coverage
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
    "cement ratio construction",
    "plastering wall tips",
    "house plan tamil",
    "rcc construction",
    "steel bar bending",
]

# YouTube Shorts trending seed keywords (high-volume searches)
SHORTS_SEEDS = [
    "construction shorts viral",
    "house building tips shorts",
    "civil engineering shorts",
    "amazing construction",
    "construction hack",
]

# Google Trends categories
TRENDS_GEO  = "IN"    # India
TRENDS_CAT  = "0"     # All categories

# High-performance evergreen hashtags (proven for civil engineering YouTube Shorts)
EVERGREEN_TAGS = [
    "#Shorts", "#civilengineering", "#construction", "#tamil",
    "#வீடுகட்டுவதுஎப்படி", "#tamilnadu", "#engineering",
    "#homeconstruction", "#buildingconstruction", "#kitchaasenterprises",
    "#concrete", "#housebuilding", "#architect", "#india",
    "#சிவில்_இன்ஜினியரிங்", "#கட்டுமானம்",
]

# Daily rotating viral tags (different set per day of week for diversity)
DAILY_VIRAL_TAGS = {
    0: ["#MondayMotivation", "#NewWeekNewBuild", "#constructionlife", "#buildingtips"],
    1: ["#TuesdayTips", "#constructionhacks", "#homedesign", "#interiordesign"],
    2: ["#WednesdayWisdom", "#engineeringfacts", "#concretetips", "#structuraldesign"],
    3: ["#ThursdayThoughts", "#architecturelovers", "#modernhouse", "#foundation"],
    4: ["#FridayVibes", "#weekendproject", "#diyconstruction", "#renovation"],
    5: ["#SaturdayBuild", "#constructionsite", "#realestate", "#homeimprovement"],
    6: ["#SundaySpecial", "#dreamhome", "#housegoals", "#constructionwork"],
}


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
                "engineer", "civil", "வீடு", "கட்டு", "சிமென்ட்",
                "home", "property", "real estate", "architecture",
            ]
            for title in titles:
                tl = title.lower()
                if any(k in tl for k in keywords):
                    relevant_terms.append(title)
            return relevant_terms[:5]
    except Exception as e:
        logger.debug(f"Google Trends RSS failed: {e}")
        return []


async def fetch_trending_hashtags(session) -> list[str]:
    """Fetch trending YouTube hashtags from autocomplete suggestions."""
    hashtag_seeds = [
        "#civilengineering", "#construction", "#housebuilding",
        "#shorts viral", "#trending construction",
    ]
    all_tags = []
    import urllib.parse
    for seed in hashtag_seeds[:3]:  # Limit to 3 for speed
        query = urllib.parse.quote(seed)
        url = f"https://suggestqueries.google.com/complete/search?client=youtube&ds=yt&q={query}&hl=en"
        try:
            async with session.get(url, timeout=6) as resp:
                if resp.status != 200:
                    continue
                text = await resp.text()
                match = re.search(r'\[.*\]', text, re.DOTALL)
                if not match:
                    continue
                data = json.loads(match.group())
                if len(data) > 1 and isinstance(data[1], list):
                    for item in data[1]:
                        term = item[0] if isinstance(item, list) else str(item)
                        # Convert to hashtag format
                        tag = "#" + term.strip().lstrip("#").replace(" ", "")
                        if len(tag) > 2 and len(tag) < 50:
                            all_tags.append(tag)
        except Exception:
            continue
    return all_tags[:10]


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


async def get_daily_trending_hashtags(topic_keywords: list[str] = None) -> list[str]:
    """
    Fetches fresh daily trending hashtags for YouTube Shorts.
    Called at publish time to ensure the most current tags are used.
    
    Combines:
    1. Day-of-week viral tags (rotate daily for freshness)
    2. Live YouTube trending hashtag suggestions
    3. Topic-specific hashtags from the video's topic
    4. Evergreen high-performance tags
    
    Returns up to 30 hashtags (YouTube allows max 30 visible hashtags).
    """
    today = datetime.now().weekday()  # 0=Monday, 6=Sunday
    
    # Start with day-specific viral tags
    daily_tags = list(DAILY_VIRAL_TAGS.get(today, []))
    
    # Add topic-specific tags
    if topic_keywords:
        for kw in topic_keywords[:5]:
            clean = kw.strip().replace(" ", "").replace("#", "")
            if clean:
                daily_tags.append(f"#{clean}")
    
    # Fetch live trending hashtags
    try:
        import aiohttp
        async with aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 (compatible; YTAutoBot/1.0)"}
        ) as session:
            live_tags = await asyncio.wait_for(
                fetch_trending_hashtags(session), timeout=15
            )
            daily_tags.extend(live_tags)
    except Exception as e:
        logger.debug(f"Live trending hashtag fetch failed: {e}")
    
    # Add evergreen tags
    daily_tags.extend(EVERGREEN_TAGS)
    
    # Deduplicate preserving order
    seen = set()
    unique = []
    for tag in daily_tags:
        tl = tag.lower().strip()
        if tl and tl not in seen and len(tl) > 1:
            seen.add(tl)
            unique.append(tag)
    
    logger.info(f"TrendsEngine: assembled {len(unique)} daily hashtags for {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][today]}")
    return unique[:30]
