import feedparser
from pathlib import Path

import spacy
from pyrosm import OSM

from processing.enrich import enrich_rss_signals
from processing.normalize_rss import normalize_rss_record
from schemas.schema import EntityInfo, RssNormalizedSignal

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ky_osm = OSM(str(PROJECT_ROOT / "kentucky-260404.osm.pbf"))
_osm_boundaries = ky_osm.get_boundaries()
_osm_pois = ky_osm.get_pois()


def _build_osm_name_set(gdf) -> set[str]:
    if gdf is None or "name" not in gdf.columns:
        return set()
    return set(gdf["name"].dropna().str.lower().str.strip().tolist())


OSM_NAMES: set[str] = (
    _build_osm_name_set(_osm_boundaries) |
    _build_osm_name_set(_osm_pois)
)

nlp = spacy.load("en_core_web_trf")

ruler = nlp.add_pipe("entity_ruler", before="ner")


def geo_info(rss_signal: RssNormalizedSignal) -> list[EntityInfo]:
    text = rss_signal.raw_text
    doc = nlp(text)
    label_details = {
        label: {
            "label": label,
            "explanation": spacy.explain(label),
        }
        for label in {ent.label_ for ent in doc.ents}
    }

    return [
        EntityInfo(
            text=ent.text,
            label=label_details[ent.label_],
        )
        for ent in doc.ents
    ]


# Weights for scoring components
_EXACT_OSM_SCORE = 1.0   # confirmed OSM name

# Label weights — GPE (city/state) is most valuable for geo relevance
_LABEL_WEIGHTS = {
    "GPE": 1.0,   # geopolitical entity — city, state, country
    "LOC": 0.85,  # non-GPE location — rivers, regions
    "FAC": 0.75,  # facility — buildings, airports
}

_GEO_THRESHOLD = 0.2


def _match_entity(entity_text: str) -> tuple[float, str]:
    """
    Try to match an entity string against the OSM name set.
    Returns (match_score, match_method) where match_score is in [0.0, 1.0].
    """
    normed = entity_text.lower().strip()

    # Exact match in OSM
    if normed in OSM_NAMES:
        return _EXACT_OSM_SCORE, "osm_exact"

    return 0.0, "no_match"


def geo_relevance(list_of_entities: list[EntityInfo]) -> float:
    """
    Compute a geographic relevance score for an article based on its
    named entities, matched against Kentucky OSM data.

    Args:
        list_of_entities: List of EntityInfo objects from geo_info().

    Returns:
        A float in [0.0, 1.0]. Higher = more geographically relevant to Kentucky.
    """
    if not list_of_entities:
        return 0.0

    geo_entities = [
        e for e in list_of_entities
        if e.label["label"] in _LABEL_WEIGHTS
    ]

    if not geo_entities:
        return 0.0

    weighted_scores = []
    for entity in geo_entities:
        match_score, method = _match_entity(entity.text)
        label_weight = _LABEL_WEIGHTS[entity.label["label"]]
        weighted_scores.append(match_score * label_weight)

    # Final score = mean of all weighted entity scores, capped at 1.0
    final_score = min(sum(weighted_scores) / len(geo_entities), 1.0)
    return round(final_score, 4)


def geo_filter(rss_signal: RssNormalizedSignal, threshold: float = _GEO_THRESHOLD) -> bool:
    """Return True when an RSS signal appears geographically relevant to Kentucky."""
    return geo_relevance(geo_info(rss_signal)) >= threshold


if __name__ == "__main__":
    # Fetch real RSS feed from a news agency
    feed_url = "https://www.lex18.com/news.rss"
    source_name = "LEX 18"

    print(f"Fetching RSS feed from {source_name}...")
    feed = feedparser.parse(feed_url)

    if not feed.entries:
        print("No entries found in RSS feed")
    else:
        # Use the first entry from the feed
        entry = feed.entries[0]

        # Normalize the entry to create a rss_signal
        signal = normalize_rss_record(entry, source=source_name)

        if signal:
            # Enrich the rss_signal with full article text
            enriched_signals = enrich_rss_signals([signal])
            signal = enriched_signals[0] if enriched_signals else signal

            print(f"Testing geo_info with rss_signal from: {signal.source}")
            print(f"Title: {signal.title}")
            print(f"Raw text: {signal.raw_text}\n")
            print("Extracted entities:")
            result = geo_info(signal)
            for entity in result:
                print(
                    f"{entity.text:<20} "
                    f"{entity.label['label']:<12} "
                    f"{entity.label['explanation']}"
                )
            print(f"\nResult: {result}")
            print("\n")
        else:
            print("Failed to create rss_signal from RSS entry")
