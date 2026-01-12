from ingestion.news import fetch_rss_feed

def test_news():
    rss_url = "https://www.lex18.com/rss"
    records = fetch_rss_feed(rss_url, "LEX18")

    print(f"News records fetched: {len(records)}")

    if records:
        print("Sample news record:")
        print(records[0])


if __name__ == "__main__":
    test_news()