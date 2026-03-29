import re

from ingestion.RSS import DISASTER_KEYWORDS

# Source reliability weights

SOURCE_CONFIDENCE: dict[str, float] = {
    "NOAA": 0.95,
    "NWS": 0.95,
    "LEX 18": 0.60,
    "WKYT": 0.60,
    "ABC 36": 0.60,
    "WLKY 32": 0.60,
    "Courier Journal": 0.65,
    "Spectrum News 1 KY": 0.60,
    "Twitter": 0.30,
}

DEFAULT_RSS_CONFIDENCE: float = 0.60
NOAA_CONFIDENCE: float = 0.95

# Blend weights for composite confidence score.
# final_confidence = (source_weight * SOURCE_BLEND) + (urgency_score * URGENCY_BLEND)
SOURCE_BLEND: float = 0.7
URGENCY_BLEND: float = 0.3

# Pre-compiled keyword pattern derived directly from DISASTER_KEYWORDS keys.
# Multi-word phrases are listed first so they match before their subwords.
_sorted_keywords = sorted(DISASTER_KEYWORDS.keys(), key=len, reverse=True)
_KEYWORD_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in _sorted_keywords) + r")\b",
    re.IGNORECASE,
)

# Dynamic max score - sum of all keyword weights; used for normalization.
_MAX_KEYWORD_SCORE: int = sum(DISASTER_KEYWORDS.values())


def _extract_keywords_and_urgency(text: str) -> tuple[list[str], float]:
    """Match disaster keywords and return a normalized urgency score.

    This wires up the DISASTER_KEYWORDS weights previously ignored
    by the regex filter.

    Args:
        text: Combined title and summary text to scan.

    Returns:
        A tuple of (matched_keywords, urgency_score) where urgency_score
        is normalized to [0.0, 1.0] relative to the maximum possible weight.
    """
    matches = [m.group(0).lower() for m in _KEYWORD_PATTERN.finditer(text)]
    keywords = list(dict.fromkeys(matches))  # deduplicate, preserve order
    raw_score = sum(DISASTER_KEYWORDS.get(kw, 0) for kw in keywords)
    urgency_score = min(raw_score / _MAX_KEYWORD_SCORE, 1.0)
    return keywords, urgency_score
