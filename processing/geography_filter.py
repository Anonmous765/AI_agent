import spacy
import pandas as pd
from pathlib import Path
from spacy.pipeline import EntityRuler
import feedparser

from schemas.schema import EntityInfo, RssNormalizedSignal
from processing.normalize_rss import normalize_rss_record
from processing.enrich import enrich_rss_signals

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GAZETTEER_CSV = PROJECT_ROOT / "gazetteer" / "Text" / "DomesticNames_KY.csv"

nlp = spacy.load("en_core_web_trf")

ruler = nlp.add_pipe("entity_ruler", before="ner")

if not GAZETTEER_CSV.exists():
    raise FileNotFoundError(f"Gazetteer CSV not found at {GAZETTEER_CSV}")

gazetteer = pd.read_csv(GAZETTEER_CSV)

def geo_info(rss_signal: RssNormalizedSignal) -> list[EntityInfo]:
    text = rss_signal.raw_text
    doc = nlp(text)

    entities = []
    for ent in doc.ents:
        entities.append(
            EntityInfo(
                text=ent.text,
                label=ent.label_,
                explanation=spacy.explain(ent.label_),
            )
        )
    return entities

def geo_relevance(list_of_entities: list[EntityInfo]) -> float:
    pass


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
                print(f"{entity.text:<20} {entity.label:<12} {entity.explanation}")
            print(f"\nResult: {result}")
            print("\n")
        else:
            print("Failed to create rss_signal from RSS entry")
