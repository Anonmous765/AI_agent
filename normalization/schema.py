"""
Shared dataclass schemas for normalized signals.

Normalization produces these canonical structures for downstream processing.
Every downstream stage — filtering, embedding, ChromaDB storage, and Gemini
context seeding — operates ONLY on these structures.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NoaaNormalizedSignal:
    """Canonical representation of a NOAA weather alert after normalization."""

    source: str
    county: str
    signal_type: str
    severity: Optional[str]
    timestamp: datetime
    confidence: float
    raw_text: str


@dataclass
class RssNormalizedSignal:
    """Normalized representation of a news-based signal.

    Attributes:
        full_text: Full article body fetched by trafilatura. Falls back to
                   raw_text (title + summary) when the fetch fails or the
                   article is paywalled. Never None after normalization —
                   always at least raw_text.
        confidence: Composite score blending source reliability and keyword
                    urgency. Range [0.0, 1.0].
    """

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
    full_text: str = field(default="")