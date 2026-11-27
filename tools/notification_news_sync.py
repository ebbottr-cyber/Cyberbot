"""Synchronize stored research articles into the local notification inbox."""
def sync_news(news_store, notification_store, *, enabled=False, limit=100):
    if not enabled:
        return {"status": "disabled"}
    result = {"published": 0, "duplicates": 0}
    for article in news_store.list(limit=limit):
        severity = "warning" if article["priority"] == "high" else "info"
        body = "\n".join([
            "Doğrulanmamış araştırma haberi; işlem sinyali değildir.",
            "Piyasa: " + article["market"],
            "Yayın: " + article["published_at"],
            article.get("summary_tr", ""),
            article["url"],
        ])
        saved = notification_store.publish(
            article["event_key"], "news", severity,
            article["title"], body, article["source"],
        )
        result["published" if saved else "duplicates"] += 1
    return result
