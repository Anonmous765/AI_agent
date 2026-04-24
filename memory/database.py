"""
Database operations for storing and querying signals using ChromaDB.
"""

import hashlib
from pathlib import Path
from typing import Any, List

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from schemas.schema import RssNormalizedSignal
from processing.semantic_filter import classify_article

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


def _ranking_score(signal: RssNormalizedSignal, classified_article: dict[str, Any]) -> float:
    """Blend source/keyword confidence with semantic relevance for stable ranking."""
    return round((signal.confidence * 0.7) + (classified_article["score"] * 0.3), 4)


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
            "confidence": round(signal.confidence, 4),
            "rank_score": _ranking_score(signal, classified_article),
            "timestamp": signal.timestamp.isoformat(),
            "title": signal.title,
            "keywords": ", ".join(signal.keywords),
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

def query_db(query: str, limit: int = 10):
    """
    Queries the vector database for relevant signals matching the search text.

    This tool should be used to search for stored articles, alerts, or other text
    in the database to provide historical context, find similar past events, or
    retrieve specific information related to a user's inquiry.

    When NOT to use tools:
        - Definitional or conceptual questions (e.g. "what does X mean?",
          "explain Y") should be answered directly from your knowledge.
        - Only call tools when the user is asking about current conditions,
          active events, or real-time data.

    Important:
        The returned matches are already ordered by priority, with the highest-
        confidence signals first. Preserve this ordering when summarizing results
        or citing them. Earlier items should be treated as more reliable and more
        important than later items unless the user explicitly asks for a different
        ordering.

    Args:
        query: The search term or natural language text to embed and find matches for.
        limit: The maximum number of relevant database results to return.

    Returns:
        A dictionary containing the original query and a `matches` list. The
        `matches` list is sorted in descending priority using confidence first,
        then rank_score, semantic score, and timestamp.
    """

    print(f"[TOOL CALLED] query_signals(topic='{query}', n_results={limit})")

    query_embedding = model.encode(
        query,
        convert_to_tensor=True,
        normalize_embeddings=True
    ).tolist()

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=limit,
        include=["documents", "metadatas"]
    )

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    ranked_matches = sorted(
        (
            {
                "document": document,
                **metadata,
            }
            for document, metadata in zip(documents, metadatas)
        ),
        key=lambda item: (
            item.get("confidence", 0.0),
            item.get("rank_score", 0.0),
            item.get("score", 0.0),
            item.get("timestamp", ""),
        ),
        reverse=True,
    )

    return {
        "query": query,
        "matches": ranked_matches[:limit],
    }
