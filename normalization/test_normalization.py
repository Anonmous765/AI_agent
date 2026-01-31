from ingestion.noaa import fetch_active_alerts
from ingestion.news import fetch_rss_feed
from normalization.normalize import normalize_noaa_record, normalize_news_record


def test_normalization(state: str = "KY"):
    print("=== NOAA NORMALIZATION ===")
    noaa_records = fetch_active_alerts(state)

    if noaa_records:
        normalized = normalize_noaa_record(noaa_records[0])
        print(f"Generated {len(normalized)} normalized signals")
        print(normalized[0])

    print("\n=== NEWS NORMALIZATION ===")
    news_records = fetch_rss_feed("https://www.lex18.com/rss", "LEX18")

    if news_records:
        normalized_news = normalize_news_record(news_records[0])
        print(normalized_news)
    else:
        print(f"No news records to normalize {state}.")


if __name__ == "__main__":
    test_normalization()