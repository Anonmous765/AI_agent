# Roadmap

Planned enhancements, adapted from course survey references (`survey §x.x`).

## Priority 4 — Memory & Reasoning

- **Memory hierarchy** (three tiers, survey §5.2):
  - Short-term: current session chat history (already exists)
  - Episodic: past sessions summarized and stored in SQLite with a sessions table
  - Long-term/semantic: ChromaDB as persistent vector store across restarts
- **Self-refinement loop** — after each Gemini response, send a follow-up validation prompt asking it to verify every claim against the provided source data (Reflexion / Self-Refine, survey §4.2.2).
- **Structured output from Gemini** — use `response_schema` with a Pydantic model to return JSON (severity, affected_counties, recommended_actions, source_links) instead of free-form Markdown.

## Priority 5 — Advanced Enhancements

- **Upgrade system prompt** using the CLEAR framework (survey §4.1.1):
  - Add explicit output format instruction
  - Add self-check instruction ("verify each claim has a source before responding")
- **Self-RAG pattern** (survey §5.1.2) — add a pre-retrieval step where Gemini decides whether retrieval is needed before querying ChromaDB, rather than always retrieving.
- **RAPTOR-style hierarchical summarization** (survey §5.1) — for long articles, build a summary tree: chunk → chunk summaries → article summary → daily digest; store all levels in ChromaDB.
- **Explore GraphRAG / LightRAG** (survey §5.1.3) — link NOAA alerts to RSS articles by shared county/event type as a knowledge graph for richer relational retrieval.
- **Evaluation scaffolding** — expand `test_normalization.py` into a proper test suite; log retrieval quality metrics (precision@K, source coverage) to measure pipeline improvements over time.
