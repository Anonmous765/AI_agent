from collections import defaultdict
from datetime import datetime
from aggregation.schema import CountyAggregate
from normalization.schema import NormalizedSignal


def aggregate_by_county(signals: list[NormalizedSignal]) -> dict[str, CountyAggregate]:
    grouped = defaultdict(list)

    # Group by county
    for signal in signals:
        grouped[signal.county].append(signal)

    aggregates = {}

    for county, county_signals in grouped.items():
        severe_count = sum(
            1 for s in county_signals
            if s.severity and s.severity.lower() == "severe"
        )

        latest_timestamp = max(s.timestamp for s in county_signals)

        aggregates[county] = CountyAggregate(
            county=county,
            signals=county_signals,
            total_signals=len(county_signals),
            severe_count=severe_count,
            latest_timestamp=latest_timestamp
        )

    return aggregates
