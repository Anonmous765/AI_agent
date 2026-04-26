"""
NOAA NWPS gauge ingestion - extraction layer only.

Responsibilities:
    - Fetch raw gauge data from the NWPS API.
    - Return raw gauge dicts for downstream storage.

This module does NOT normalize, transform, or construct dataclass instances.
All transformation and storage is handled by database/gauges.py.
"""

from __future__ import annotations

import time

import requests

BASE_URL = "https://api.water.noaa.gov"
HEADERS = {
    "User-Agent": "KY-Damage-Agent/1.0 (vedansh.kakkar@gmail.com)",
    "Accept": "application/json",
}

def fetch_gauge(
    lid: str,
    *,
    timeout: tuple[float, float] = (5, 15),
    retries: int = 3,
    backoff_seconds: float = 1.5,
) -> dict | None:
    """Fetch a single raw gauge dict by LID from the NWPS API.

    Args:
        lid: The Location ID of the gauge (e.g. ``"PKYK2"``).
        timeout: ``(connect_timeout, read_timeout)`` passed to ``requests``.
        retries: Number of total attempts before surfacing the failure.
        backoff_seconds: Base delay used between retry attempts.

    Returns:
        Raw gauge dict, or ``None`` if the gauge does not exist (404).

    Raises:
        requests.HTTPError: If the NWPS API returns a non-2xx, non-404 response.
        requests.Timeout: If all attempts exceed the configured timeout.
    """
    url = f"{BASE_URL}/nwps/v1/gauges/{lid}"
    last_error: requests.RequestException | None = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt == retries:
                raise
            time.sleep(backoff_seconds * attempt)
    else:
        raise RuntimeError(
            "NWPS gauge fetch failed without raising an exception."
        ) from last_error

    return response.json()

if __name__ == "__main__":
    print(fetch_gauge("ABPK2"))