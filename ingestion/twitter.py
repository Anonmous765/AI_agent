"""
Twitter/X ingestion — extraction layer only.

Responsibilities:
    - Maintain the disaster search query (DISASTER_QUERY).
    - Fetch raw tweet data from the Twitter v2 API via Tweepy.
    - Return raw tweet dicts for downstream normalization.

This module does NOT normalize, filter, or construct dataclass instances.
All transformation and filtering is handled by normalization/normalize.py.
"""

from __future__ import annotations

import os
from pathlib import Path
import re

import dotenv
try:
    import tweepy
except ImportError:  # pragma: no cover - handled at runtime for local testability
    tweepy = None

dotenv.load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

MAX_TWEETS = 5

DISASTER_QUERY = (
    "("
    "disaster OR emergency OR evacuation OR flood OR flooding OR hail OR landslide OR outage OR "
    "\"power outage\" OR rescue OR \"severe weather\" OR storm OR thunderstorm OR tornado OR warning OR "
    "\"weather alert\" OR wildfire OR \"wind damage\""
    ") "
    "("
    "Kentucky OR #KYwx OR Louisville OR \"Bowling Green\" OR Frankfort OR Paducah OR Owensboro OR "
    "Covington OR \"eastern Kentucky\" OR \"western Kentucky\" OR KY"
    ") "
    "-is:retweet -is:reply lang:en"
)

TWEET_FIELDS = ["created_at", "author_id", "public_metrics", "geo"]

KENTUCKY_PATTERNS = [
    re.compile(r"\bkentucky\b"),
    re.compile(r"#kywx\b"),
    re.compile(r"\bky\b"),
    re.compile(r"\blouisville\b"),
    re.compile(r"\bbowling green\b"),
    re.compile(r"\bfrankfort\b"),
    re.compile(r"\bpaducah\b"),
    re.compile(r"\bowensboro\b"),
    re.compile(r"\bcovington\b"),
]

DISASTER_PATTERNS = [
    re.compile(r"\bdisaster\b"),
    re.compile(r"\bemergency\b"),
    re.compile(r"\bevacuation\b"),
    re.compile(r"\bflash flood\b"),
    re.compile(r"\bflood(?:ing)?\b"),
    re.compile(r"\bhail(?:stones)?\b"),
    re.compile(r"\blandslide\b"),
    re.compile(r"\boutage\b"),
    re.compile(r"\bpower outage\b"),
    re.compile(r"\brescue\b"),
    re.compile(r"\bsevere weather\b"),
    re.compile(r"\bstorms?\b"),
    re.compile(r"\bthunderstorms?\b"),
    re.compile(r"\btornado(?:es)?\b"),
    re.compile(r"\bwarning\b"),
    re.compile(r"\bweather alert\b"),
    re.compile(r"\bwildfire\b"),
    re.compile(r"\bwind damage\b"),
]


def _build_client() -> "tweepy.Client":
    """Create a Tweepy client with a clear error when local config is incomplete."""
    if tweepy is None:
        raise RuntimeError("tweepy is not installed. Install it with `pip install tweepy`.")

    bearer_token = os.getenv("BEARER_TOKEN")
    consumer_key = os.getenv("API_KEY")
    consumer_secret = os.getenv("API_KEY_SECRET")

    if not bearer_token:
        raise RuntimeError("Missing BEARER_TOKEN in .env.")

    return tweepy.Client(
        bearer_token=bearer_token,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
    )


def _normalize_limit(limit: int) -> int:
    """Clamp API requests to the small test budget for this project."""
    return max(1, min(limit, MAX_TWEETS))


def _is_kentucky_disaster_tweet(tweet: dict) -> bool:
    """Lightweight local filter to remove obvious false positives from the broad query."""
    text = str(tweet.get("text", "")).lower()
    has_kentucky_signal = any(pattern.search(text) for pattern in KENTUCKY_PATTERNS)
    has_disaster_signal = any(pattern.search(text) for pattern in DISASTER_PATTERNS)
    return has_kentucky_signal and has_disaster_signal


def fetch_raw_tweets(
    query: str = DISASTER_QUERY,
    max_results: int = MAX_TWEETS,
) -> list[dict]:
    """Fetch up to 5 raw tweet dicts from the last 7 days via a single API call.

    Args:
        query: Twitter search query string.
        max_results: Number of tweets to return, clamped to 1–5.

    Returns:
        A list of raw tweet attribute dicts. Empty list if no results.

    Raises:
        RuntimeError: If Tweepy or API credentials are unavailable.
        tweepy.TweepyException: On API or authentication errors.
    """
    client = _build_client()
    response = client.search_recent_tweets(
        query=query,
        max_results=_normalize_limit(max_results),
        tweet_fields=TWEET_FIELDS,
    )
    tweets = response.data or []
    filtered = [tweet.data for tweet in tweets if _is_kentucky_disaster_tweet(tweet.data)]
    return filtered[:MAX_TWEETS]


def fetch_raw_tweets_paginated(
    query: str = DISASTER_QUERY,
    total: int = MAX_TWEETS,
) -> list[dict]:
    """Paginate through recent tweets up to 5 Kentucky disaster-related results.

    Args:
        query: Twitter search query string.
        total: Maximum number of tweets to collect, clamped to 1–5.

    Returns:
        A list of raw tweet attribute dicts.

    Raises:
        RuntimeError: If Tweepy or API credentials are unavailable.
        tweepy.TweepyException: On API or authentication errors.
    """
    client = _build_client()
    total = _normalize_limit(total)
    tweets = []
    for page in tweepy.Paginator(
        client.search_recent_tweets,
        query=query,
        tweet_fields=TWEET_FIELDS,
        max_results=10,
        limit=1,
    ):
        if page.data:
            for tweet in page.data:
                if _is_kentucky_disaster_tweet(tweet.data):
                    tweets.append(tweet.data)
        if len(tweets) >= total:
            break
    return tweets[:total]


if __name__ == "__main__":
    print("=== Kentucky disaster test fetch (max 5 tweets) ===\n")
    tweets = fetch_raw_tweets_paginated(total=MAX_TWEETS)
    print(f"Fetched {len(tweets)} tweet(s).\n")
    for tweet in tweets:
        metrics = tweet.get("public_metrics") or {}
        print(f"[{tweet.get('created_at')}] author:{tweet.get('author_id')}")
        print(f"  {tweet.get('text')}")
        print(
            f"  Likes: {metrics.get('like_count', 0)}  "
            f"Retweets: {metrics.get('retweet_count', 0)}"
        )
        print()
