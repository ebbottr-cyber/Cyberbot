"""Opt-in durable inbox delivery; no device push or trading."""
def drain_news(news_store, notification_store, *, enabled=False, limit=100):
    if not enabled:
        return {"status":"disabled"}
    result = {"published":0,"duplicates":0,"retry":0}
    for article in news_store.pending_delivery(limit=limit):
        key = article["event_key"]
        body = "\n".join(["Doğrulanmamış araştırma haberi; işlem sinyali değildir.",
                          "Piyasa: "+article["market"], "Yayın: "+article["published_at"],
                          article.get("summary_tr",""), article["url"]])
        try:
            saved = notification_store.publish(key,"news",
                "warning" if article["priority"]=="high" else "info",
                article["title"],body,article["source"])
        except Exception:
            news_store.finish_delivery(key,success=False)
            result["retry"] += 1
            continue
        news_store.finish_delivery(key,success=True)
        result["published" if saved else "duplicates"] += 1
    return result
