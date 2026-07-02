"""
NOAA alert ingestion - extraction layer only.

Responsibilities:
    - Fetch raw alert data from the NWS API.
    - Return raw property dicts for downstream normalization.

This module does NOT normalize, transform, or construct dataclass instances.
All transformation is handled by normalization/normalize.py.
"""

from __future__ import annotations

import time

import requests

BASE_URL = "https://api.weather.gov"
HEADERS = {
    "User-Agent": "KY-Damage-Agent/1.0 (vedansh.kakkar@gmail.com)",
    "Accept": "application/geo+json",
}


def fetch_raw_alerts(
    area: str = "KY",
    *,
    timeout: tuple[float, float] = (5, 15),
    retries: int = 3,
    backoff_seconds: float = 1.5,
) -> list[dict]:
    """Fetch raw alert property dicts from the NWS API.

    Args:
        area: NWS area code to query (default: "KY").
        timeout: ``(connect_timeout, read_timeout)`` passed to ``requests``.
        retries: Number of total attempts before surfacing the failure.
        backoff_seconds: Base delay used between retry attempts.

    Returns:
        A list of raw ``properties`` dicts from each alert feature.
        Features with no ``areaDesc`` are excluded.

    Raises:
        requests.HTTPError: If the NWS API returns a non-2xx response.
        requests.Timeout: If all attempts exceed the configured timeout.
    """
    url = f"{BASE_URL}/alerts/active/area/{area}"
    last_error: requests.RequestException | None = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt == retries:
                raise
            time.sleep(backoff_seconds * attempt)
    else:
        raise RuntimeError("NOAA alert fetch failed without raising an exception.") from last_error

    features = response.json().get("features", [])

    return [
        props
        for feature in features
        if (props := feature.get("properties", {})) and props.get("areaDesc")
    ]


if __name__ == "__main__":
    alerts = fetch_raw_alerts()
    print(f"Fetched {len(alerts)} raw alert(s).")
    for a in alerts[:2]:
        print(a.get("headline", "No headline"))
