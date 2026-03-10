import os
import json
from dataclasses import asdict
from datetime import datetime

import feedparser
from dotenv import load_dotenv
from google import genai

from ingestion.noaa import fetch_active_alerts
from ingestion.RSS import RSS_FEEDS, rss_filter
from normalization.schema import RssNormalizedSignal

from rich.console import Console
from rich.markdown import Markdown

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

useful_articles = []

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

Your output should be concise, factual, and actionable when possible.
"""

def parse_entry_timestamp(entry: dict) -> datetime:
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if published:
        return datetime(*published[:6])
    return datetime.utcnow()


def rss_signal_to_json(signal: RssNormalizedSignal) -> str:
    payload = asdict(signal)
    payload["timestamp"] = signal.timestamp.isoformat()
    return json.dumps(payload)


for region in RSS_FEEDS.values():
    for station in region.values():
        articles = feedparser.parse(station["url"])
        article = rss_filter(articles)
        if not article:
            continue

        useful_articles.append(article)

history = []
history.extend(
    {"role": "user", "parts": [{"text": rss_signal_to_json(a)}]}
    for a in useful_articles
)

history.extend(
    {"role": "user", "parts": [{"text": json.dumps(advisory)}]}
    for advisory in fetch_active_alerts()
)

chat = client.chats.create(model="gemini-3-flash-preview", history=history)
chat.send_message(system_prompt)

console = Console()

while True:
    message = input("Enter a message: ")
    response = chat.send_message(message)

    console.print(Markdown(response.text))

    if message.lower() == "exit":
        break