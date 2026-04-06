"""Shared dataclass schemas for normalized signals and extracted entities."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class EntityInfo:
    """Structured representation of a named entity extracted from text."""

    text: str
    label: str
    explanation: Optional[str]


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
    full_text: str = field(default="")
    embeddings: list[float] = None
