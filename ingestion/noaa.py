"""
NOAA alert ingestion — extraction layer only.

Responsibilities:
    - Fetch raw alert data from the NWS API.
    - Return raw property dicts for downstream normalization.

This module does NOT normalize, transform, or construct dataclass instances.
All transformation is handled by normalization/normalize.py.
"""

import requests

BASE_URL = "https://api.weather.gov"
HEADERS = {
    "User-Agent": "KY-Damage-Agent/1.0 (vedansh.kakkar@gmail.com)",
    "Accept": "application/geo+json",
}


def fetch_raw_alerts(area: str = "KY") -> list[dict]:
    """Fetch raw alert property dicts from the NWS API.

    Args:
        area: NWS area code to query (default: "KY").

    Returns:
        A list of raw ``properties`` dicts from each alert feature.
        Features with no ``areaDesc`` are excluded.

    Raises:
        requests.HTTPError: If the NWS API returns a non-2xx response.
        requests.Timeout: If the request exceeds the 10-second timeout.
    """
    url = f"{BASE_URL}/alerts/active/area/{area}"
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()

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