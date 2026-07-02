# KY Damage Agent

**Kentucky Disaster Situational Awareness AI**

An intelligent conversational agent that ingests live disaster and weather data from multiple sources, filters it for Kentucky relevance, and surfaces insights via a Gemini-powered streaming chat interface.

## Overview

KY Damage Agent is a real-time situational awareness system built for disaster response and monitoring in Kentucky. It:

- **Ingests** live data from 8 Kentucky RSS feeds (news sources), NOAA weather alerts, 184+ Kentucky flood gauges, Twitter/X disaster reports, and web search
- **Filters** all incoming signals for Kentucky geographic relevance using NER + OpenStreetMap data and semantic topic classification
- **Stores** indexed signals in a persistent ChromaDB vector database for fast semantic search
- **Responds** via a Gemini AI agent with 5 callable tools: vector DB queries, NOAA alerts, flood gauge status, web search, and live gauge refresh
- **Streams** responses to the web UI in real-time, with visible tool-call events for transparency

**Academic Context:** Built as a Web Mining lab project with production-grade architecture.

## Architecture & Data Flow

```
1. Ingestion (startup + background)
   ├─ RSS feeds (8 Kentucky news outlets) → feedparser
   ├─ NOAA alerts (api.weather.gov/alerts/active/area/KY)
   ├─ NWPS gauges (api.water.noaa.gov) — 184 Kentucky locations
   ├─ Twitter/X (Tweepy v2 API, disaster + Kentucky keywords)
   └─ Web search (Tavily API on-demand)

2. Processing Pipeline
   ├─ Normalize → dataclass (timestamp, source, confidence score)
   ├─ Semantic filter → SentenceTransformer embeddings vs. 14 emergency categories
   ├─ Geography filter → spaCy NER + OSM Kentucky place names
   └─ Enrich → fetch full article text via trafilatura

3. Storage
   ├─ ChromaDB vector store (cosine similarity, persistent)
   ├─ SQLite chat_store.sqlite3 (sessions + messages)
   └─ SQLite ky_gauges.db (gauge readings, crest records, computed status)

4. Gemini LLM Agent
   ├─ System prompt: Kentucky-only scope, professional tone, strict citations
   ├─ 5 tools: query_vector_db(), fetch_noaa_alerts(), query_gauges(),
   │           query_gauge_crests(), web_search()
   └─ Autonomously calls tools based on user intent

5. UI
   └─ Vanilla JS single-page app → Flask SSE streaming → word-by-word text + tool-call events
```

See `docs/architecture.pdf` for the full system diagram.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Web Server** | Flask |
| **LLM** | Google Gemini (gemini-3-flash-preview) |
| **Vector Store** | ChromaDB (persistent, cosine) |
| **Embeddings** | sentence-transformers/all-MiniLM-L6-v2 |
| **NER / Geo Filter** | spaCy en_core_web_trf (transformer model) |
| **Map Data** | pyrosm + Kentucky OSM (145 MB PBF file) |
| **Article Scraping** | trafilatura |
| **RSS** | feedparser |
| **Persistence** | SQLite (sqlite3) |
| **Weather APIs** | NWS (api.weather.gov), NOAA NWPS (api.water.noaa.gov) |
| **Web Search** | Tavily API |
| **Social Media** | Tweepy (Twitter v2 API) |
| **Frontend** | Vanilla JS + CSS, marked.js, Google Fonts |

## Project Structure

```
KY_Damage_Agent/
├── README.md
├── LICENSE
├── pyproject.toml                 # Installable package definition
├── requirements.txt               # Pinned runtime dependencies
├── .env.example                   # Template for required API keys
│
├── src/ky_damage_agent/
│   ├── paths.py                   # Single source of truth for data/.env paths
│   │
│   ├── frontend/
│   │   ├── app.py                 # Flask web server + REST/SSE endpoints
│   │   └── templates/
│   │       └── index.html         # Single-page chat UI (vanilla JS)
│   │
│   ├── llm_reasoning/
│   │   ├── gemini.py              # Core AI agent, system prompt, tool defs, CLI loop
│   │   └── gemini_chat.py         # Chat factory, message persistence, SSE helpers
│   │
│   ├── ingestion/
│   │   ├── rss.py                 # 8 Kentucky feed catalog + fetcher
│   │   ├── noaa.py                # NWS alert API client
│   │   ├── nwps.py                # NOAA gauge data fetcher
│   │   ├── twitter.py             # Twitter/X disaster tweet crawler
│   │   └── web_search.py          # Tavily API client
│   │
│   ├── processing/
│   │   ├── normalize_noaa.py      # NOAA alert → dataclass + scoring
│   │   ├── normalize_rss.py       # RSS entry → dataclass + confidence
│   │   ├── scoring.py             # Source weights, urgency, composite confidence
│   │   ├── semantic_filter.py     # SentenceTransformer topic classification
│   │   ├── geography_filter.py    # spaCy NER + OSM Kentucky relevance
│   │   └── enrich.py              # Concurrent full-text article fetch
│   │
│   ├── memory/
│   │   ├── database.py            # ChromaDB vector store: embed, upsert, query
│   │   ├── chat_store.py          # SQLite session/message CRUD
│   │   ├── gauges.py              # SQLite gauge readings + computed status view
│   │   └── seed_gauges.py         # One-time seeder: fetch + populate 184 gauges
│   │
│   └── schemas/
│       └── schema.py              # Shared dataclasses
│
├── docs/
│   ├── architecture.pdf           # System architecture diagram
│   └── ROADMAP.md                 # Planned enhancements
│
├── notebooks/
│   └── testing.ipynb              # Jupyter notebook for manual testing (not tracked)
│
└── data/                          # Runtime data, not tracked in version control
    ├── database/
    │   ├── chat_store.sqlite3     # Persisted chat sessions
    │   └── ky_gauges.db           # Gauge readings + crest history
    ├── chroma_db/                 # Persistent vector store
    └── kentucky-260404.osm.pbf    # OpenStreetMap Kentucky data (145 MB)
```

## Setup

### Prerequisites

- Python 3.10+
- pip
- Virtual environment (recommended)

### Installation

1. **Clone and navigate:**
   ```bash
   git clone <repo-url>
   cd KY_Damage_Agent
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # macOS/Linux
   # or: venv\Scripts\activate  # Windows
   ```

3. **Install the package in editable mode:**
   ```bash
   pip install -e .
   ```
   This installs all dependencies (from `requirements.txt`) and registers the `ky-damage-agent` console command. Alternatively, run `pip install -r requirements.txt` without installing the package — in that case use `python -m ky_damage_agent.frontend.app` to start the server (see below).

4. **Download spaCy transformer model:**
   ```bash
   python -m spacy download en_core_web_trf
   ```

5. **Download the Kentucky OSM extract** and place it at `data/kentucky-260404.osm.pbf` (used by the geography filter for place-name matching).

6. **Seed the gauge database** (one-time, fetches 184 Kentucky gauges from NWPS API):
   ```bash
   python -m ky_damage_agent.memory.seed_gauges
   ```
   Note: If you skip this, the `/chat/stream` endpoint will auto-fetch + cache gauge data on first query.

### Environment Variables

Copy `.env.example` to `.env` in the project root and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google GenAI API key (get from [ai.google.dev](https://ai.google.dev)) |
| `TAVILY_API_KEY` | Tavily web search API key |
| `API_KEY` | Twitter consumer API key |
| `API_KEY_SECRET` | Twitter consumer API secret |
| `ACCESS_TOKEN` | Twitter access token |
| `ACCESS_TOKEN_SECRET` | Twitter access token secret |
| `BEARER_TOKEN` | Twitter bearer token |

## Running the App

### Web UI (Flask)

```bash
ky-damage-agent
# or: python -m ky_damage_agent.frontend.app
```

- Opens on `http://localhost:5000`
- Single-page chat interface with session persistence
- Light/dark theme (OS preference + toggle)
- Real-time tool-call visibility (see which data sources are being queried)
- Markdown rendering + word-by-word text animation

### CLI Mode (Standalone)

For interactive testing without the web UI:

```bash
python -m ky_damage_agent.llm_reasoning.gemini
```

- Direct conversation loop with the Gemini agent
- Full tool output printed to console
- Rich library formatting for readability

## API Endpoints

### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sessions` | List all chat sessions |
| POST | `/sessions` | Create a new session |
| GET | `/sessions/<id>` | Get session + all messages |
| PATCH | `/sessions/<id>` | Rename a session |
| DELETE | `/sessions/<id>` | Delete session (cascade deletes messages) |

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat` | Non-streaming chat (returns JSON reply) |
| POST | `/chat/stream` | **SSE streaming** chat (recommended) |

#### SSE Events (`/chat/stream`)

```
tool_call      → {"name": "query_db", "label": "Querying knowledge base"}
tool_done      → {"name": "query_db"}
text           → {"chunk": "word or whitespace"}
done           → {"session_id": "...", "session": {...}}
error          → {"error": "message"}
```

## Data Sources

- **RSS (8 outlets):** LEX18, WKYT, ABC36, Spectrum KY, WLKY, Courier Journal, Louisville Business First, Voice-Tribune
- **NOAA Alerts:** Real-time National Weather Service Kentucky alerts (api.weather.gov)
- **Flood Gauges:** 184 Kentucky USGS gauges via NOAA NWPS API (auto-refresh every 2 hours)
- **Twitter/X:** Disaster + Kentucky keywords (Tweepy v2 API, capped at 5 recent tweets)
- **Web Search:** On-demand via Tavily API (called by Gemini when context lacks answer)

## Scoring & Filtering

**Confidence Scores:** `source_weight * 0.7 + urgency_score * 0.3`
- NOAA alerts: 0.95
- Local TV: 0.60
- Twitter: 0.30

**Semantic Filter:** SentenceTransformer embeddings vs. 14 emergency categories (flood, tornado, hazmat, etc.) — threshold 0.40

**Geographic Filter:** spaCy NER + OSM Kentucky place names — threshold 0.20

**Low-scoring signals are dropped** before ChromaDB upsert.

## Notable Features

- **Transparent Tool Calls:** Every Gemini tool invocation emits SSE events, so the UI shows which data sources are being consulted in real-time.
- **Auto-Refresh Gauges:** On first `query_gauges()` call, all 184 Kentucky gauge readings are fetched in parallel (10-worker thread pool) and cached for 2 hours.
- **Persistent Sessions:** Chat history lives in SQLite with foreign-key cascade deletes.
- **Geography-Aware:** Loads a real 145 MB Kentucky OSM file at import and uses transformer-based NER for high-precision location extraction.
- **Auto-Session Titles:** First user message is truncated to 60 chars and used as session title (no extra Gemini call).
- **Markdown UI:** Full CommonMark rendering in the browser via marked.js.

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for planned enhancements (three-tier memory, Self-RAG, RAPTOR, GraphRAG).

## Development

### Running Tests

Jupyter notebook (`notebooks/testing.ipynb`) contains manual test cases for each module.

### Modifying Data Sources

Edit `src/ky_damage_agent/ingestion/rss.py` to add/remove RSS feeds or change disaster keywords.

### Adjusting Filters

- **Semantic threshold:** `src/ky_damage_agent/processing/semantic_filter.py` (default 0.40)
- **Geographic threshold:** `src/ky_damage_agent/processing/geography_filter.py` (default 0.20)
- **Source weights:** `src/ky_damage_agent/processing/scoring.py`

## License

MIT — see [LICENSE](LICENSE).

## Contact

Built as a Web Mining lab project.
