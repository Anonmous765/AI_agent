import requests
from datetime import datetime

BASE_URL = "https://api.weather.gov"
HEADERS = {
    "User-Agent": "KY-Damage-Agent/1.0 (contact@example.com)",
    "Accept": "application/geo+json"
}

def fetch_active_alerts(area="KY"):
    """
    Fetch active weather alerts for a given area (e.g., KY).
    Returns a list of raw ingestion records.
    """
    url = f"{BASE_URL}/alerts/active/area/{area}"
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()

    data = response.json()
    records = []

    for feature in data.get("features", []):
        props = feature.get("properties", {})

        records.append({
            "source": "NOAA",
            "raw_text": props.get("headline", "") + " " + props.get("description", ""),
            "timestamp": props.get("sent", datetime.utcnow().isoformat()),
            "metadata": {
                "event": props.get("event"),
                "severity": props.get("severity"),
                "certainty": props.get("certainty"),
                "areas": props.get("areaDesc")
            }
        })

    return records
