from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NormalizedSignal:
    """
    Canonical representation of a real-world signal after normalization.
    Every downstream stage operates ONLY on this structure.
    """

    source: str
    county: str
    signal_type: str
    severity: Optional[str]
    timestamp: datetime
    confidence: float
    raw_text: str
