"""
Interactive Gemini-based situational awareness assistant.

This script:
- Collects normalized RSS items and NOAA alerts.
- Seeds them into a Gemini chat session.
- Provides a CLI loop for user queries.

Usage:
    python "LLM Reasoning/Gemini.py"

Notes:
    Type "exit" to quit the interactive session.

Environment:
    GEMINI_API_KEY: API key for the Google GenAI client.
"""

import os
import json
from dataclasses import asdict
from datetime import datetime

import feedparser
from dotenv import load_dotenv
from google import genai

from ingestion.noaa import fetch_active_alerts
from ingestion.RSS import RSS_FEEDS, rss_filter
from normalization.schema import NoaaNormalizedSignal, RssNormalizedSignal

from rich.console import Console
from rich.markdown import Markdown

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

# System instructions for the safety-focused assistant.
system_prompt = """
You are an AI safety and situational-awareness agent.

Your role is to interpret structured data related to weather events, natural disasters,
and other potentially dangerous conditions, and convert it into clear, accurate,
human-readable information.

You must:
- Base your reasoning strictly on the provided data (no speculation).
- Identify severity, urgency, affected regions, and potential risk to people or property.
- Use precise language appropriate for public safety communication.
- Avoid exaggeration, panic-inducing phrasing, or hallucinated details.
- If data is incomplete or ambiguous, explicitly state the uncertainty.

Make sure to cite your sources when presenting information in case the user wants to follow up on their own. 
The citations should be directly next to the information presented, so it is clear which information came from which source.
If the source is a news agency, include the link to the news article(if available).

Your output should be concise, factual, and actionable when possible.
"""

def parse_entry_timestamp(entry: dict) -> datetime:
    """Extract the published/updated timestamp from a feedparser entry.

    Args:
        entry: Feedparser entry mapping with parsed timestamp fields.

    Returns:
        A UTC datetime from the entry or the current UTC time when missing.
    """
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if published:
        return datetime(*published[:6])
    return datetime.utcnow()


def rss_signal_to_json(signal: RssNormalizedSignal) -> str:
    """Serialize a normalized RSS signal to JSON with an ISO 8601 timestamp.

    Args:
        signal: Normalized RSS signal dataclass instance.

    Returns:
        JSON-encoded string with an ISO 8601 timestamp.
    """
    payload = asdict(signal)
    payload["timestamp"] = signal.timestamp.isoformat()
    return json.dumps(payload)

def noaa_signal_to_json(signal: NoaaNormalizedSignal) -> str:
    """Serialize a normalized NOAA signal to JSON with an ISO 8601 timestamp.

    Args:
        signal: Normalized NOAA signal dataclass instance.

    Returns:
        JSON-encoded string with an ISO 8601 timestamp.
    """
    payload = asdict(signal)
    payload["timestamp"] = signal.timestamp.isoformat()
    return json.dumps(payload)


useful_articles: list[RssNormalizedSignal] = []

for region in RSS_FEEDS.values():
    for station in region.values():
        articles = feedparser.parse(station["url"])
        article = rss_filter(articles)
        if not article:
            continue

        useful_articles.extend(article)

# Seed the chat history with normalized RSS items and NOAA advisories.
history = []
history.extend(
    {"role": "user", "parts": [{"text": rss_signal_to_json(a)}]}
    for a in useful_articles
)

history.extend(
    {"role": "user", "parts": [{"text": noaa_signal_to_json(alert)}]}
    for alert in fetch_active_alerts()
)

# Start the chat and prime it with the system prompt.
chat = client.chats.create(model="gemini-3-flash-preview", history=history)
chat.send_message(system_prompt)

console = Console()

if __name__ == "__main__":
    while True:
        # Interactive loop: accept user queries and render Markdown responses.
        message = input("Enter a message: ")
        response = chat.send_message(message)

        console.print(Markdown(response.text))

        if message.lower() == "exit":
            break
