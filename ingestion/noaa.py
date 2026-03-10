"""
NOAA alert ingestion helpers.

Fetches active weather alerts from the National Weather Service API and
returns normalized signals suitable for downstream reasoning.
"""

import requests
from datetime import datetime

from normalization.schema import NoaaNormalizedSignal

BASE_URL = "https://api.weather.gov"
HEADERS = {
    "User-Agent": "KY-Damage-Agent/1.0 (vedansh.kakkar@gmail.com)",
    "Accept": "application/geo+json"
}

NOAA_CONFIDENCE = 0.95

def _parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamps from NOAA, defaulting to current UTC on failure."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()

def fetch_active_alerts(area="KY"):
    """Fetch active weather alerts for a given area (e.g., KY).

    Args:
        area: NWS area code to query (default: "KY").

    Returns:
        A list of normalized NOAA alert signals.
    """
    url = f"{BASE_URL}/alerts/active/area/{area}"
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()

    data = response.json()
    signals = []

    for feature in data.get("features", []):
        props = feature.get("properties", {})
        counties = props.get("areaDesc") or ""

        if not counties:
            continue

        raw_text = f"{props.get('headline', '')} {props.get('description', '')}".strip()
        timestamp = _parse_timestamp(props.get("sent", ""))

        for county in counties.split(";"):
            signals.append(
                NoaaNormalizedSignal(
                    source="NOAA",
                    county=county.strip(),
                    signal_type=props.get("event", "Weather Alert"),
                    severity=props.get("severity"),
                    timestamp=timestamp,
                    confidence=NOAA_CONFIDENCE,
                    raw_text=raw_text,
                )
            )

    return signals

if __name__ == "__main__":
    print(fetch_active_alerts())
