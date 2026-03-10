import feedparser
import requests
import apscheduler
from normalization.schema import RssNormalizedSignal
import re
from datetime import datetime

RSS_FEEDS = {
    "central_kentucky": {
        "LEX18": {
            "station":  "LEX 18",
            "call_sign": "WLEX",
            "network":  "NBC",
            "url":      "https://www.lex18.com/news.rss"
        },
        "WKYT": {
            "station":  "WKYT",
            "call_sign": "WKYT",
            "network":  "CBS",
            "url":      "https://www.wkyt.com/rss"
        },
        "ABC36": {
            "station":  "ABC 36",
            "call_sign": "WTVQ",
            "network":  "ABC",
            "url":      "https://wtvq.com/feed"
        },
        "SPECTRUM_KY": {
            "station":  "Spectrum News 1 KY",
            "call_sign": "N/A",
            "network":  "Cable",
            "url":      "https://spectrumlocalnews.com/services/contentfeed.do?collectionId=9777"
        },
    },
    "louisville": {
        "WLKY": {
            "station":  "WLKY 32",
            "call_sign": "WLKY",
            "network":  "CBS",
            "url":      "https://www.wlky.com/topstories-rss"
        },
        "COURIER_JOURNAL": {
            "station":  "Courier Journal",
            "call_sign": "N/A",
            "network":  "Print",
            "url":      "https://www.courier-journal.com/rss/"
        },
        "LOUISVILLE_BUSINESS_FIRST": {
            "station":  "Louisville Business First",
            "call_sign": "N/A",
            "network":  "Print",
            "url":      "https://feeds.bizjournals.com/bizj_louisville"
        },
        "VOICE_TRIBUNE": {
            "station":  "Voice-Tribune",
            "call_sign": "N/A",
            "network":  "Print",
            "url":      "https://voice-tribune.com/blog-feed.xml"
        },
    }
}

DISASTER_KEYWORDS = {
    # keyword -> weight
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

def rss_filter(feed: feedparser.FeedParserDict) -> RssNormalizedSignal | None:
    articles = feed["entries"]
    disaster_article = None
    pattern = re.compile(
        
        r"\b(?:flash flood|severe thunderstorm|winter storm|road closed|power outage|boil water|"
        r"flooding|flood|tornado|storm|ice|snow|evacuation|shelter|river|crest|landslide|emergency)\b",
        re.IGNORECASE
    )

    for article in articles:
        title = article.get("title") or ""
        summary = article.get("summary") or ""
        text = f"{title} {summary}".strip()
        if not re.search(pattern, text):
            continue

        matches = [match.group(0).lower() for match in pattern.finditer(text)]
        keywords = list(dict.fromkeys(matches))
        published = article.get("published_parsed") or article.get("updated_parsed")
        timestamp = datetime(*published[:6]) if published else datetime.utcnow()
        author = article.get("author", "None found")
        source = feed.get("feed", "News Agency").get("title") or feed.get("href", "News Agency")

        disaster_article = RssNormalizedSignal(
            source=source,
            author=author,
            signal_type="News Report",
            title=title,
            link=article.get("link", "None found"),
            timestamp=timestamp,
            keywords=keywords,
            raw_text=text,
        )

    return disaster_article


if __name__ == "__main__":
    for x in RSS_FEEDS.values():
        for y in x.items():
            print(y[1]['url'])
            print(rss_filter(feedparser.parse(y[1]['url'])))


