import feedparser
from datetime import datetime

KEYWORDS = [
    "snow", "ice", "storm", "power", "outage",
    "road", "closed", "emergency"
]

def fetch_rss_feed(url, source_name):
    """
    Fetch articles from an RSS feed and return raw ingestion records.
    """
    feed = feedparser.parse(url)
    records = []

    for entry in feed.entries:
        text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()

        # Optional relevance filter
        if not any(k in text for k in KEYWORDS):
            continue

        records.append({
            "source": source_name,
            "raw_text": f"{entry.get('title', '')}. {entry.get('summary', '')}",
            "timestamp": entry.get("published", datetime.utcnow().isoformat()),
            "metadata": {
                "link": entry.get("link")
            }
        })

    return records
