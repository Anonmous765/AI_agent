import chromadb
import hashlib
from pathlib import Path
from dotenv import load_dotenv

from normalization.schema import RssNormalizedSignal
from normalization.semantic_filter import classify_article

load_dotenv()

p = Path('.')
chroma_client = chromadb.PersistentClient(p / '.chroma_db')


collection = chroma_client.get_or_create_collection(
    name="signals",
    metadata={"hnsw:space": "cosine"},
)
def rss_signal_storage(signals: list[RssNormalizedSignal]):
    ids, embeddings, documents, metadatas = [], [], [], []

    for signal in signals:
        classified_article = classify_article(title=signal.title, summary=signal.raw_text)

        if not classified_article["relevant"]:
            continue

        text = f"{signal.title}. {signal.raw_text}"
        full_hash = hashlib.sha256(text.encode()).hexdigest()

        ids.append(full_hash)
        embeddings.append(classified_article["article_emb"])
        documents.append(text)
        metadatas.append({
            "source": signal.source,
            "label": classified_article["label"],
            "score": round(classified_article["score"], 4),
            "timestamp": signal.timestamp.isoformat(),
            "link": signal.link or ""  # guard against None
        })

    if ids:
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        print(f"Upserted {len(ids)} signal(s). Collection total: {collection.count()}")