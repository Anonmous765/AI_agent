"""NOAA normalization helpers."""

from datetime import datetime

from models.schema import NoaaNormalizedSignal
from processing.scoring import NOAA_CONFIDENCE


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 / RFC timestamps to a datetime.

    Single source of truth for NOAA timestamp parsing.

    Args:
        ts: Timestamp string with optional "Z" UTC suffix.

    Returns:
        Parsed datetime, or current UTC time if parsing fails.
    """
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()


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
