from concurrent.futures import ThreadPoolExecutor
from trafilatura import fetch_url, extract
from models.schema import RssNormalizedSignal


def _enrich_rss_signal(signal: RssNormalizedSignal) -> RssNormalizedSignal:
    """Enrich a RssNormalizedSignal with full text."""

    if signal.link == "None found":
        return signal

    downloaded = fetch_url(url=signal.link)
    if downloaded is None:
        return signal

    signal.full_text = full_article if (full_article := extract(downloaded)) else signal.raw_text
    return signal


def enrich_rss_signals(signals: list[RssNormalizedSignal]) -> list[RssNormalizedSignal]:
    """Enrich a list of RssNormalizedSignals with full article text.

    Args:
        signals: List of normalized RSS signals to enrich.

    Returns:
        List of enriched signals with full_text populated where available.
    """
    with ThreadPoolExecutor() as executor:
        return list(executor.map(_enrich_rss_signal, signals))