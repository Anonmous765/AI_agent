"""
Shared dataclass schemas for normalized signals.

Normalization produces these canonical structures for downstream processing.
"""

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
    """Normalized representation of a news-based signal."""

    source: str
    author: str
    signal_type: str
    severity: Optional[str]
    title: str
    link: str
    timestamp: datetime
    confidence: float
    keywords: list[str]
    raw_text: str
