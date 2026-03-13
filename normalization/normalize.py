"""
Normalization helpers for NOAA alerts and news signals.

These functions convert raw ingestion records into shared dataclasses used
by downstream reasoning and ranking steps.
"""

from datetime import datetime
from normalization.schema import NoaaNormalizedSignal, RssNormalizedSignal


# Source reliability weights
SOURCE_CONFIDENCE = {
    "NOAA": 0.95,
    "NWS": 0.95,
    "LEX18": 0.60,
    "WKYT": 0.60,
    "WDRB": 0.60,
    "Twitter": 0.30,
}

DEFAULT_NEWS_CONFIDENCE = 0.60


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO/RFC timestamps to a datetime.

    Args:
        ts: Timestamp string, typically ISO 8601 with optional "Z" suffix.

    Returns:
        Parsed datetime or current UTC time if parsing fails.
    """
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()


def normalize_noaa_record(record: dict) -> list[NoaaNormalizedSignal]:
    """Convert a NOAA ingestion record into one or more normalized signals.

    Args:
        record: Raw NOAA record with "metadata" and "timestamp" fields.

    Returns:
        A list of normalized signals, one per county listed in the record.
    """
    metadata = record.get("metadata", {})
    counties = metadata.get("areas", "")

    if not counties:
        return []

    signals = []

    for county in counties.split(";"):
        signals.append(
            NoaaNormalizedSignal(
                source="NOAA",
                county=county.strip(),
                signal_type=metadata.get("event", "Weather Alert"),
                severity=metadata.get("severity"),
                timestamp=parse_timestamp(record.get("timestamp", "")),
                confidence=SOURCE_CONFIDENCE["NOAA"],
                raw_text=record.get("raw_text", "")
            )
        )

    return signals


def normalize_news_record(record: dict) -> RssNormalizedSignal:
    """Convert a news ingestion record into a normalized RSS signal.

    This accepts either a pre-extracted dict or a feedparser entry. Missing
    fields fall back to safe defaults when the feed does not provide them.

    Args:
        record: Raw news record or feedparser entry mapping.

    Returns:
        A normalized RSS signal with all fields populated.
    """
    source = (
        record.get("source")
        or record.get("feed_title")
        or record.get("feed", {}).get("title")
        or "Unknown"
    )
    author = record.get("author") or record.get("byline") or "Unknown"
    title = record.get("title") or record.get("headline") or ""
    link = record.get("link") or record.get("url") or ""
    signal_type = record.get("signal_type") or "News Report"

    raw_text = record.get("raw_text")
    if not raw_text:
        summary = record.get("summary") or record.get("description") or ""
        raw_text = f"{title} {summary}".strip()

    confidence = record.get("confidence")
    if confidence is None:
        confidence = SOURCE_CONFIDENCE.get(source, DEFAULT_NEWS_CONFIDENCE)

    keywords = record.get("keywords")
    if isinstance(keywords, str):
        keywords = [item.strip() for item in keywords.split(",") if item.strip()]
    if not keywords:
        tags = record.get("tags") or []
        keywords = [
            tag.get("term")
            for tag in tags
            if isinstance(tag, dict) and tag.get("term")
        ]
    if not keywords:
        keywords = []

    timestamp = record.get("timestamp")
    if isinstance(timestamp, datetime):
        parsed_timestamp = timestamp
    elif isinstance(timestamp, str) and timestamp:
        parsed_timestamp = parse_timestamp(timestamp)
    elif isinstance(timestamp, tuple):
        parsed_timestamp = datetime(*timestamp[:6])
    else:
        published = record.get("published_parsed") or record.get("updated_parsed")
        parsed_timestamp = datetime(*published[:6]) if published else datetime.utcnow()

    return RssNormalizedSignal(
        source=source,
        author=author,
        signal_type=signal_type,
        title=title,
        link=link,
        timestamp=parsed_timestamp,
        confidence=confidence,
        keywords=keywords,
        raw_text=raw_text,
    )
