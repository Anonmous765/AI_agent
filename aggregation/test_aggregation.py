from ingestion.noaa import fetch_active_alerts
from normalization.normalize import normalize_noaa_record
from aggregation.aggregate import aggregate_by_county


def test_aggregation():
    raw = fetch_active_alerts("KY")

    normalized = []
    for record in raw:
        normalized.extend(normalize_noaa_record(record))

    aggregates = aggregate_by_county(normalized)

    for county, agg in aggregates.items():
        print(county)
        print(f"  Total signals: {agg.total_signals}")
        print(f"  Severe alerts: {agg.severe_count}")
        print(f"  Latest update: {agg.latest_timestamp}")

    print("\n=== END ===")


if __name__ == "__main__":
    test_aggregation()
