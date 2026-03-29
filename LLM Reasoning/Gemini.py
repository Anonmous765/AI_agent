"""
Interactive Gemini-based situational awareness assistant.

This script:
- Fetches raw RSS and NOAA data via the ingestion layer.
- Normalizes and filters signals via the normalization layer.
- Seeds a Gemini chat session with the resulting signals.
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

from dotenv import load_dotenv
from google import genai
from google.genai import types
from rich.console import Console
from rich.markdown import Markdown

from ingestion.noaa import fetch_raw_alerts
from ingestion.RSS import RSS_FEEDS, fetch_raw_articles
from normalization.Normalize import normalize_noaa_record, normalize_rss_record
from normalization.schema import NoaaNormalizedSignal, RssNormalizedSignal
from normalization.enrich import enrich_rss_signals
from memory.database import rss_signal_storage, query_db
from normalization.semantic_filter import classify_article

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

**Operational Guidelines:**
- **Strict Accuracy:** Base your reasoning strictly on the provided data (no speculation).
- **Risk Assessment:** Identify severity, urgency, affected regions, and potential risk to people or property.
- **Precise Communication:** Use language appropriate for public safety communication. Avoid exaggeration, panic-inducing phrasing, or hallucinated details.
- **Transparency:** If data is incomplete or ambiguous, explicitly state the uncertainty with professional honesty.

**Citations:**
- Cite your sources directly next to the information presented so it is clear which information came from which source.
- If the source is a news agency, include the link to the news article (if available).

**Source Links:**
- Every news article citation MUST render the actual URL from the `link` field 
  in the provided data, formatted exactly like this:
  (Source: WLKY — https://www.wlky.com/article/example)
- Never substitute a label like "WLKY Link" in place of the actual URL.
- If no `link` field is present in the data, write: (Source: [name] — No link available)
- Do not construct, infer, or guess any URL not present verbatim in the data.

**Output Style:**
Your output should be concise, factual, and actionable when possible.
"""


# Serialization helpers

def _signal_to_json(signal: RssNormalizedSignal | NoaaNormalizedSignal) -> str:
    """Serialize any normalized signal to a JSON string with ISO 8601 timestamp."""
    payload = asdict(signal)
    payload["timestamp"] = signal.timestamp.isoformat()
    return json.dumps(payload)


# Ingestion + normalization

rss_signals: list[RssNormalizedSignal] = []

for region in RSS_FEEDS.values():
    for station in region.values():
        source, entries = fetch_raw_articles(station["url"])
        for entry in entries:
            signal = normalize_rss_record(entry, source)
            if signal:
                relevance = classify_article(signal)["relevant"]
                if relevance:
                    rss_signals.append(signal)
# Add full text to each signal and store in database
rss_signals = enrich_rss_signals(rss_signals)
rss_signal_storage(rss_signals)

noaa_signals: list[NoaaNormalizedSignal] = []
for props in fetch_raw_alerts():
    noaa_signals.extend(normalize_noaa_record(props))


# Seed Gemini chat history

history = []
history.extend(
    {"role": "user", "parts": [{"text": _signal_to_json(s)}]}
    for s in rss_signals
)
history.extend(
    {"role": "user", "parts": [{"text": _signal_to_json(s)}]}
    for s in noaa_signals
)

chat = client.chats.create(
    model="gemini-3-flash-preview",
    config=types.GenerateContentConfig(system_instruction=system_prompt,
                                       tools=[query_db]),
    history=history,
)

console = Console()

# Interactive loop

if __name__ == "__main__":
    print(f"Seeded context: {len(rss_signals)} RSS signal(s), {len(noaa_signals)} NOAA alert(s).")
    while True:
        message = input("Enter a message: ")
        if message.lower() == "exit":
            break
        response = chat.send_message(message)
        console.print(Markdown(response.text))