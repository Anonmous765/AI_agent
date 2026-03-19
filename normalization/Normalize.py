"""
Normalization layer — transformation, filtering, and composite scoring.

Responsibilities:
    - Parse timestamps (single source of truth for both NOAA and RSS).
    - Convert raw ingestion records into canonical dataclass instances.
    - Filter RSS entries for disaster relevance via keyword matching.
    - Compute composite confidence scores blending source reliability
      and keyword urgency weights.
    - Set full_text default (falls back to raw_text until trafilatura runs).

This is the ONLY module that constructs NoaaNormalizedSignal or
RssNormalizedSignal instances. Ingestion modules return raw dicts/entries.
"""

import re
from datetime import datetime
from typing import Optional

from ingestion.RSS import DISASTER_KEYWORDS
from normalization.schema import NoaaNormalizedSignal, RssNormalizedSignal
from normalization.semantic_filter import classify_article

# Source reliability weights

SOURCE_CONFIDENCE: dict[str, float] = {
    "NOAA": 0.95,
    "NWS": 0.95,
    "LEX 18": 0.60,
    "WKYT": 0.60,
    "ABC 36": 0.60,
    "WLKY 32": 0.60,
    "Courier Journal": 0.65,
    "Spectrum News 1 KY": 0.60,
    "Twitter": 0.30,
}

DEFAULT_RSS_CONFIDENCE: float = 0.60
NOAA_CONFIDENCE: float = 0.95

# Blend weights for composite confidence score.
# final_confidence = (source_weight * SOURCE_BLEND) + (urgency_score * URGENCY_BLEND)
SOURCE_BLEND: float = 0.7
URGENCY_BLEND: float = 0.3

# Pre-compiled keyword pattern derived directly from DISASTER_KEYWORDS keys.
# Multi-word phrases are listed first so they match before their subwords.
_sorted_keywords = sorted(DISASTER_KEYWORDS.keys(), key=len, reverse=True)
_KEYWORD_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in _sorted_keywords) + r")\b",
    re.IGNORECASE,
)

# Dynamic max score — sum of all keyword weights; used for normalization.
_MAX_KEYWORD_SCORE: int = sum(DISASTER_KEYWORDS.values())


# Shared utilities

def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 / RFC timestamps to a datetime.

    Single source of truth for both NOAA and RSS timestamp parsing.

    Args:
        ts: Timestamp string with optional "Z" UTC suffix.

    Returns:
        Parsed datetime, or current UTC time if parsing fails.
    """
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()


def _extract_keywords_and_urgency(text: str) -> tuple[list[str], float]:
    """Match disaster keywords and return a normalized urgency score.

    This wires up the DISASTER_KEYWORDS weights previously ignored
    by the regex filter.

    Args:
        text: Combined title and summary text to scan.

    Returns:
        A tuple of (matched_keywords, urgency_score) where urgency_score
        is normalized to [0.0, 1.0] relative to the maximum possible weight.
    """
    matches = [m.group(0).lower() for m in _KEYWORD_PATTERN.finditer(text)]
    keywords = list(dict.fromkeys(matches))  # deduplicate, preserve order
    raw_score = sum(DISASTER_KEYWORDS.get(kw, 0) for kw in keywords)
    urgency_score = min(raw_score / _MAX_KEYWORD_SCORE, 1.0)
    return keywords, urgency_score


# NOAA normalization

def normalize_noaa_record(props: dict) -> list[NoaaNormalizedSignal]:
    """Convert a raw NWS alert properties dict into normalized signals.

    One signal is emitted per county listed in ``areaDesc``.

    Args:
        props: Raw ``properties`` dict from a NWS GeoJSON alert feature.

    Returns:
        A list of normalized NOAA signals, one per county.
        Returns an empty list if ``areaDesc`` is absent or empty.
    """
    counties = props.get("areaDesc") or ""
    if not counties:
        return []

    raw_text = f"{props.get('headline', '')} {props.get('description', '')}".strip()
    timestamp = parse_timestamp(props.get("sent", ""))

    return [
        NoaaNormalizedSignal(
            source="NOAA",
            county=county.strip(),
            signal_type=props.get("event", "Weather Alert"),
            severity=props.get("severity"),
            timestamp=timestamp,
            confidence=NOAA_CONFIDENCE,
            raw_text=raw_text,
        )
        for county in counties.split(";")
        if county.strip()
    ]


# ---------------------------------------------------------------------------
# RSS normalization
# ---------------------------------------------------------------------------

def normalize_rss_record(
        entry: dict,
        source: str,
) -> Optional[RssNormalizedSignal]:
    """Filter and normalize a raw feedparser entry into an RSS signal.

    Filtering:  Returns None if the entry contains no disaster keywords.
    Scoring:    Composite confidence = (source_reliability * 0.7)
                                     + (keyword_urgency   * 0.3)
    full_text:  Defaults to raw_text (title and summary). Trafilatura will
                overwrite this field in a later enrichment step.

    Args:
        entry:  Raw feedparser entry dict.
        source: Feed source name returned by fetch_raw_articles().

    Returns:
        A normalized RSS signal, or None if not disaster-relevant.
    """
    title = entry.get("title") or ""
    summary = entry.get("summary") or ""
    raw_text = f"{title} {summary}".strip()

    keywords, urgency_score = _extract_keywords_and_urgency(raw_text)

    article_info = classify_article(title, summary, threshold=0.40)

    if not article_info["relevant"]:
        return None



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


if __name__ == "__main__":
    from ingestion.RSS import fetch_raw_articles

    source, entries = fetch_raw_articles("https://www.lex18.com/news.rss")

    testArticle = classify_article(entries[0].get("title") or "", entries[0].get("summary") or "")
    print(".")
