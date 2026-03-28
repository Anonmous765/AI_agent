"""
Database operations for storing and querying signals using ChromaDB.
"""

import hashlib
from pathlib import Path
from typing import List

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from normalization.schema import RssNormalizedSignal
from normalization.semantic_filter import classify_article

load_dotenv()

# ChromaDB client
DB_PATH = Path('.') / '.chroma_db'
chroma_client = chromadb.PersistentClient(path=str(DB_PATH))

# Embedding model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Get or create the vector collection
collection = chroma_client.get_or_create_collection(
    name="signals",
    metadata={"hnsw:space": "cosine"},
)


def rss_signal_storage(signals: List[RssNormalizedSignal]) -> None:
    """
    Classifies, embeds, and stores a list of RSS signals into the vector database.
    
    Args:
        signals: A list of normalized RSS signals to process and store.
    """
    ids = []
    embeddings = []
    documents = []
    metadatas = []

    for signal in signals:
        classified_article = classify_article(signal)

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