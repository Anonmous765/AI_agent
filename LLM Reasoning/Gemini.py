import os
from dotenv import load_dotenv
from google import genai
import feedparser
import json
from ingestion.noaa import fetch_active_alerts

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

articles = feedparser.parse("https://www.lex18.com/news.rss")


useful_articles = []

# Create a function for returning the dict. with all relevant info
for e in articles.get("entries", []):
    item = {
        "title": e.get("title", ""),
        "link": e.get("link", ""),
        "summary": e.get("summary", ""),
        "published": e.get("published", ""),
        "author": e.get("author", ""),
    }
    item = {key: value for key, value in item.items() if value}
    if item:
        useful_articles.append(item)

history = []
history.extend(
    {"role": "user", "parts": [{"text": json.dumps(a)}]}
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
