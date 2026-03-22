import chromadb
import hashlib
from pathlib import Path
from dotenv import load_dotenv

from normalization.schema import RssNormalizedSignal
from normalization.semantic_filter import classify_article

load_dotenv()

p = Path('.')
chroma_client = chromadb.PersistentClient(p / 'chroma_db')


collection = chroma_client.get_or_create_collection(
    name="signals",
    metadata={"hnsw:space": "cosine"},
)
def rss_signal_storage(signals: list[RssNormalizedSignal]):
    for signal in signals:
        full_hash = hashlib.sha256(signal.title.encode()).hexdigest()
        classified_article = classify_article(title=signal.title, summary=signal.raw_text)

        # adding signal to chroma
        collection.upsert(ids=full_hash,
                          embeddings=[signal.embeddings],
                          documents=f"{signal.title}. {signal.raw_text}",
                          metadatas=[{
                              "source": signal.source,
                              "label": classified_article["label"],
                              "score": round(classified_article["score"], 4),
                              "timestamp": signal.timestamp.isoformat(),
                              "link": signal.link
                          }])