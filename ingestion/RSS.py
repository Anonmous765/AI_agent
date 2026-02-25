import feedparser
import requests
import apscheduler
from normalization.schema import RssNormalizedSignal
import re

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

def rss_filter(feed: feedparser.FeedParserDict) -> list[feedparser.FeedParserDict] | None:
    articles = feed["entries"]
    disaster_articles = []
    pattern = re.compile(
        r"\b(?:flash flood|severe thunderstorm|winter storm|road closed|power outage|boil water|"
        r"flooding|flood|tornado|storm|ice|snow|evacuation|shelter|river|crest|landslide|emergency)\b",
        re.IGNORECASE
    )

    for article in articles:
        if re.search(pattern, article.get("summary", "") or re.search(pattern, article.get("title", "")):
            disaster_articles.append(article)

    return disaster_articles if len(articles) > 0 else None