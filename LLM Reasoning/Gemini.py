import os
import json
from dataclasses import asdict
from datetime import datetime

import feedparser
from dotenv import load_dotenv
from google import genai

from ingestion.noaa import fetch_active_alerts
from ingestion.RSS import RSS_FEEDS
from normalization.schema import RssNormalizedSignal

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

useful_articles = []

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
        source = station.get("station") or station.get("call_sign") or "Unknown"
        for e in articles.get("entries", []):
            title = e.get("title", "")
            link = e.get("link", "")
            summary = e.get("summary", "")
            author = e.get("author", "")
            raw_text = " ".join(part for part in (title, summary) if part).strip()
            if not any([title, link, summary, author]):
                continue

            useful_articles.append(
                RssNormalizedSignal(
                    source=source,
                    author=author or "Unknown",
                    signal_type="News Report",
                    title=title,
                    link=link,
                    timestamp=parse_entry_timestamp(e),
                    keywords=[],
                    raw_text=raw_text,
                )
            )

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

if __name__ == '__main__':
    while True:
        message = input("Enter a message: ")
        response = chat.send_message(message)
        print(response.text)

        if message.lower() == "exit":
            break
