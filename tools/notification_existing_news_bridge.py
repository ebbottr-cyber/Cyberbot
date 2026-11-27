"""Read existing approved RSS metadata without fetching or modifying source data."""
from cyberbot.news_feed import read, FEEDS
from tools.notification_news_pipeline import process_news

def normalize_market(market):
    return {"FUTURES": "BINANCE_FUTURES"}.get(market, market)

def sync_existing_news(news_store, *, enabled=False, provider=None, ai_enabled=False):
    if not enabled:
        return {"status": "disabled"}
    counts = {"saved": 0, "duplicate": 0, "busy": 0, "invalid": 0}
    for row in read("ALL")["items"]:
        try:
            key = row["source_id"]
            if key not in FEEDS or row.get("origin") != "official_rss":
                raise ValueError("Unsupported source")
            record = {"source": key.upper(), "source_id": row["id"],
                      "title": row["label"], "url": row["url"],
                      "published_at": row["event_at"],
                      "market": normalize_market(row["market"]), "summary": ""}
            result = process_news(news_store, record, enabled=True,
                                  provider=provider, ai_enabled=ai_enabled)
            counts[result["status"]] += 1
        except (ValueError, KeyError, TypeError):
            counts["invalid"] += 1
    return {"status": "completed", **counts, "research_only": True,
            "orders_enabled": False}
