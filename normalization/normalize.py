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


def parse_timestamp(ts: str) -> datetime:
    """
    Convert ISO / RFC timestamps to datetime.
    Falls back to now() if parsing fails.
    """
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()


def normalize_noaa_record(record: dict) -> list[NoaaNormalizedSignal]:
    """
    Convert a single NOAA ingestion record into one or more NormalizedSignals.
    NOAA alerts may apply to multiple counties.
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
    """
    Convert a news ingestion record into a NormalizedSignal.
    County extraction is deferred or coarse at this stage.
    """
    source = record.get("source", "Unknown")

    return RssNormalizedSignal(
        source=source,
        county="Unknown",  # refined later (NER / rules)
        signal_type="News Report",
        severity=None,
        timestamp=parse_timestamp(record.get("timestamp", "")),
        confidence=SOURCE_CONFIDENCE.get(source, 0.5),
        raw_text=record.get("raw_text", "")
    )
