"""
RSS ingestion — extraction layer only.

Responsibilities:
    - Maintain the feed catalog (RSS_FEEDS).
    - Define disaster keyword weights (DISASTER_KEYWORDS).
    - Fetch raw feedparser entries from a given feed URL.

This module does NOT normalize, filter, or construct dataclass instances.
All transformation and filtering is handled by normalization/normalize.py.
"""

import feedparser

RSS_FEEDS = {
    "central_kentucky": {
        "LEX18": {
            "station": "LEX 18",
            "call_sign": "WLEX",
            "network": "NBC",
            "url": "https://www.lex18.com/news.rss",
        },
        "WKYT": {
            "station": "WKYT",
            "call_sign": "WKYT",
            "network": "CBS",
            "url": "https://www.wkyt.com/rss",
        },
        "ABC36": {
            "station": "ABC 36",
            "call_sign": "WTVQ",
            "network": "ABC",
            "url": "https://wtvq.com/feed",
        },
        "SPECTRUM_KY": {
            "station": "Spectrum News 1 KY",
            "call_sign": "N/A",
            "network": "Cable",
            "url": "https://spectrumlocalnews.com/services/contentfeed.do?collectionId=9777",
        },
    },
    "louisville": {
        "WLKY": {
            "station": "WLKY 32",
            "call_sign": "WLKY",
            "network": "CBS",
            "url": "https://www.wlky.com/topstories-rss",
        },
        "COURIER_JOURNAL": {
            "station": "Courier Journal",
            "call_sign": "N/A",
            "network": "Print",
            "url": "https://www.courier-journal.com/rss/",
        },
        "LOUISVILLE_BUSINESS_FIRST": {
            "station": "Louisville Business First",
            "call_sign": "N/A",
            "network": "Print",
            "url": "https://feeds.bizjournals.com/bizj_louisville",
        },
        "VOICE_TRIBUNE": {
            "station": "Voice-Tribune",
            "call_sign": "N/A",
            "network": "Print",
            "url": "https://voice-tribune.com/blog-feed.xml",
        },
    },
}

# Domain-expert urgency weights.
# Used in normalization/normalize.py to compute a keyword urgency score
# that blends with source confidence into the final composite confidence field.
DISASTER_KEYWORDS: dict[str, int] = {
    "flood": 5,
    "flooding": 5,
    "flash flood": 6,
    "tornado": 6,
    "severe thunderstorm": 4,
    "storm": 2,
    "winter storm": 4,
    "ice": 3,
    "snow": 2,
    "evacuation": 7,
    "shelter": 4,
    "road closed": 3,
    "power outage": 3,
    "boil water": 6,
    "river": 2,
    "crest": 3,
    "landslide": 5,
    "emergency": 4,
}


def fetch_raw_articles(url: str) -> tuple[str, list[dict]]:
    """Fetch raw feedparser entries from an RSS feed URL.

    Args:
        url: RSS feed URL to parse.

    Returns:
        A tuple of (source_name, entries) where source_name is the feed's
        self-reported title (or the URL as fallback) and entries is the raw
        list of feedparser entry dicts.
    """
    feed = feedparser.parse(url)
    feed_info = feed.get("feed") or {}
    source = feed_info.get("title") or feed.get("href") or "News Agency"
    entries = feed.get("entries") or []
    return source, entries


if __name__ == "__main__":
    for region in RSS_FEEDS.values():
        for station in region.values():
            source, entries = fetch_raw_articles(station["url"])
            print(f"{source}: {len(entries)} entries fetched")