from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NoaaNormalizedSignal:
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

@dataclass
class RssNormalizedSignal:
    source: str
    author: str
    signal_type: str
    title: str
    link: str
    timestamp: datetime
    keywords: list[str]
    raw_text: str

