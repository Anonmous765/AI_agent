from dataclasses import dataclass
from typing import List
from datetime import datetime
from normalization.schema import NormalizedSignal


@dataclass
class CountyAggregate:
    county: str
    signals: List[NormalizedSignal]

    total_signals: int
    severe_count: int
    latest_timestamp: datetime

