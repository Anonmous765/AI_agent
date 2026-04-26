"""
Interactive Gemini-based situational awareness assistant.

This script:
- Fetches raw RSS data at startup and stores it in the vector database.
- Provides Gemini with tools to query the database and fetch live NOAA alerts.
- Provides a CLI loop for user queries.

Usage:
    python "LLM Reasoning/Gemini.py"

Notes:
    Type "exit" to quit the interactive session.

Environment:
    GEMINI_API_KEY: API key for the Google GenAI client.
"""

import os
from dataclasses import asdict

from dotenv import load_dotenv
from google import genai
from google.genai import types
import requests
from rich.console import Console
from rich.markdown import Markdown

from ingestion.noaa import fetch_raw_alerts
from memory.gauges import query_gauges, query_crests
from ingestion.RSS import RSS_FEEDS, fetch_raw_articles
from processing.normalize_noaa import normalize_noaa_record
from processing.normalize_rss import normalize_rss_record
from schemas.schema import NoaaNormalizedSignal, RssNormalizedSignal
from processing.enrich import enrich_rss_signals
from memory.database import rss_signal_storage, query_db
from processing.semantic_filter import classify_article
from processing.geography_filter import geo_filter

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

system_prompt = r"""
You are an AI safety and situational-awareness agent.

**Persona & Tone:**
- **Professional Courtesy:** Maintain a polite, composed, and formal demeanor, reminiscent of a trusted news anchor or a dedicated butler.
- **Interpersonal Grace:** Acknowledge greetings (e.g., "Good morning," "Hello") with appropriate cordiality before proceeding to the data.
- **Calm Authority:** Your tone should be steady and reassuring, providing facts without inducing unnecessary alarm.

**Role & Responsibilities:**
Your role is to interpret structured data related to weather events, natural disasters, and other potentially dangerous conditions, and convert it into clear, accurate, human-readable information.

**Geographic Scope:**
- Report only information that is directly related to **Kentucky**.
- Include events that occur in Kentucky or clearly affect Kentucky residents, property, infrastructure, travel, or public safety.
- Ignore events outside Kentucky unless the provided data explicitly states they have a direct impact on Kentucky.
- If none of the provided data is relevant to Kentucky, state that clearly and briefly.

**Operational Guidelines:**
- **Strict Accuracy:** Base your reasoning strictly on the provided data (no speculation).
- **Kentucky Relevance First:** Before reporting anything, determine whether the information is relevant to Kentucky. If it is not, do not include it.
- **Risk Assessment:** Identify severity, urgency, affected Kentucky regions, and potential risk to people or property.
- **Precise Communication:** Use language appropriate for public safety communication. Avoid exaggeration, panic-inducing phrasing, or hallucinated details.
- **Transparency:** If data is incomplete or ambiguous, explicitly state the uncertainty with professional honesty.

**Citations:**
- Cite your sources directly next to the information presented so it is clear which information came from which source.
- If the source is a news agency, include the link to the news article (if available).

**Source Links:**
- Every news article citation MUST render the actual URL from the `link` field
  in the provided data, formatted exactly like this:
  (Source: WLKY - https://www.wlky.com/article/example)
- Never substitute a label like "WLKY Link" in place of the actual URL.
- If no `link` field is present in the data, write: (Source: [name] - No link available)
- Do not construct, infer, or guess any URL not present verbatim in the data.

**Data Retrieval Tools:**
You have access to three tools for retrieving situational data. Use them proactively — do not wait to be asked:
- `query_db`: Search stored RSS news articles in the vector database. Use this to find relevant news reports, historical context, or specific incidents whenever a user asks about current events.
- `fetch_noaa_alerts`: Fetch live, active weather alerts from the National Weather Service. Use this whenever the user asks about weather warnings, watches, advisories, or emergency alerts.
- `query_gauges`: Query the Kentucky flood gauge database for current river and creek water levels. Use this whenever the user asks about river stages, flood levels, water heights, gauge status, or how close any waterway is to flood stage. Accepts optional `county` and `status_filter` parameters to narrow results.

Always call one or more tools to gather relevant data before formulating your answer. Do not answer from memory or prior context alone.

**Output Style:**
- Keep the output concise, factual, and actionable when possible.
- Focus only on Kentucky-relevant developments.
- If there is no Kentucky-relevant threat, incident, or advisory in the data, say so plainly.
"""


def _populate_rss_database() -> int:
    """Fetch, filter, enrich, and store RSS signals in the vector DB. Returns count stored."""
    signals: list[RssNormalizedSignal] = []

    for region in RSS_FEEDS.values():
        for station in region.values():
            try:
                source, entries = fetch_raw_articles(station["url"])
            except Exception as exc:  # noqa: BLE001
                print(f"Warning: failed to fetch RSS feed {station['url']}: {exc}")
                continue

            for entry in entries:
                signal = normalize_rss_record(entry, source)
                if signal:
                    relevance = classify_article(signal)["relevant"]
                    is_geo_relevant = geo_filter(signal)
                    if relevance and is_geo_relevant:
                        signals.append(signal)

    signals = enrich_rss_signals(signals)
    rss_signal_storage(signals)
    return len(signals)


def fetch_noaa_alerts() -> dict:
    """
    Fetches all live, active NOAA/NWS weather alerts for Kentucky.

    Use this tool whenever the user asks about current weather warnings, watches,
    advisories, or active emergency alerts. This tool reaches out to the National
    Weather Service API in real time and returns the latest data for the entire state.

    Returns:
        A dictionary with:
        - "count": total number of active alerts.
        - "alerts": list of alert dicts, each with source, county, signal_type,
                    severity, timestamp (ISO 8601), confidence, and raw_text.
    """
    print("[TOOL CALLED] fetch_noaa_alerts()")

    try:
        raw_alerts = fetch_raw_alerts()
    except requests.RequestException as exc:
        return {"error": str(exc), "count": 0, "alerts": []}

    signals: list[NoaaNormalizedSignal] = []
    for props in raw_alerts:
        signals.extend(normalize_noaa_record(props))

    alerts = []
    for s in signals:
        payload = asdict(s)
        payload["timestamp"] = s.timestamp.isoformat()
        alerts.append(payload)

    return {"count": len(alerts), "alerts": alerts}


def create_chat():
    """Create a Gemini chat session with all data-retrieval tools registered."""
    return client.chats.create(
        model="gemini-3-flash-preview",
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[query_db, fetch_noaa_alerts, query_gauges, query_crests],
        ),
    )


def initialize_chat():
    """Populate the RSS database and create the Gemini chat session."""
    count = _populate_rss_database()
    print(f"Startup: stored {count} RSS signal(s) in the vector database.")
    return create_chat()


# Interactive loop

if __name__ == "__main__":
    chat = initialize_chat()
    console = Console()
    while True:
        message = input("Enter a message: ")
        if message.lower() == "exit":
            break
        response = chat.send_message(message)
        console.print(Markdown(response.text))
