"""RSS normalization helpers."""

from datetime import datetime
from typing import Optional

from models.schema import RssNormalizedSignal
from processing.scoring import (
    DEFAULT_RSS_CONFIDENCE,
    SOURCE_BLEND,
    SOURCE_CONFIDENCE,
    URGENCY_BLEND,
    _extract_keywords_and_urgency,
)


def normalize_rss_record(
        entry: dict,
        source: str,
) -> Optional[RssNormalizedSignal]:
    """
    Normalizes an RSS feed entry into the RssNormalizedSignal format. This function processes
    the input RSS feed entry, extracts relevant information, evaluates its importance using
    keywords and urgency, and returns a normalized signal if the article is classified as
    relevant.

    :param entry: The RSS feed entry represented as a dictionary containing fields such as
                  "title", "summary", "published_parsed", and "author".
    :type entry: dict
    :param source: The source of the RSS feed represented as a string.
    :type source: str
    :return: A normalized RssNormalizedSignal object if the article is deemed relevant,
             otherwise None.
    :rtype: Optional[RssNormalizedSignal]
    """
    title = entry.get("title") or ""
    summary = entry.get("summary") or ""
    raw_text = f"{title} {summary}".strip()

    keywords, urgency_score = _extract_keywords_and_urgency(raw_text)

    published = entry.get("published_parsed") or entry.get("updated_parsed")
    timestamp = datetime(*published[:6]) if published else datetime.utcnow()

    source_reliability = SOURCE_CONFIDENCE.get(source, DEFAULT_RSS_CONFIDENCE)
    confidence = round(
        (source_reliability * SOURCE_BLEND) + (urgency_score * URGENCY_BLEND),
        4,
    )

    return RssNormalizedSignal(
        source=source,
        author=entry.get("author") or "None found",
        signal_type="News Report",
        severity=None,  # enriched later by semantic stage
        title=title,
        link=entry.get("link") or "None found",
        timestamp=timestamp,
        confidence=confidence,
        keywords=keywords,
        raw_text=raw_text,
        full_text=raw_text,  # trafilatura overwrites this in enrichment step
    )
