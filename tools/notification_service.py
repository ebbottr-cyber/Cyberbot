"""Explicit service cycle; no automatic startup or trading integration."""
import os
from datetime import datetime, timezone
from contextlib import closing
from tools.notification_news_sources import poll_source
from tools.notification_news_retry import drain_news
from tools.notification_calendar import emit_reminders
from tools.notification_policy import route
from tools.notification_preferences import morning_digest

def run_cycle(store, push_store, queue, *, events=(), sources=(), user_agent=None,
              sender=None, preferences=None, enabled=False, push_enabled=False, now=None, news_store=None):
    if not enabled:
        return {"status": "disabled"}
    now = now or datetime.now(timezone.utc)
    result = {"status": "ok", "sources": {}}
    for source in sources:
        try:
            result["sources"][source] = poll_source(store, source, enabled=True, user_agent=user_agent)
        except Exception as exc:
            result["sources"][source] = {"status": "error", "type": type(exc).__name__}
    result["existing_news_bridge"] = {"status": "disabled"}
    if news_store is not None and os.getenv("CYBERBOT_NOTIFICATION_NEWS_BRIDGE") == "1":
        try:
            from tools.notification_existing_news_bridge import sync_existing_news
            result["existing_news_bridge"] = sync_existing_news(news_store, enabled=True)
        except Exception as exc:
            result["existing_news_bridge"] = {"status": "error", "type": type(exc).__name__}
    if news_store is not None:
        try:
            result["research_news"] = drain_news(news_store, store, enabled=True)
        except Exception as exc:
            result["research_news"] = {"status":"error","type":type(exc).__name__}
    else:
        result["research_news"] = {"status":"disabled"}
    result["calendar"] = emit_reminders(store, events, now)
    result["digest_created"] = morning_digest(store, now)
    settings = preferences.load() if preferences is not None else {}
    push_enabled = push_enabled and settings.get("push_enabled", True)
    if push_enabled and sender is not None:
        subscriptions = push_store.subscriptions()
        # Bounded initial integration; durable cursor and digest scheduling remain separate.
        for notification in store.list(limit=500, unread=True):
            if route(notification, now, push_enabled=True, quiet_start=settings.get("quiet_start", "00:30"), quiet_end=settings.get("quiet_end", "08:00"), muted=settings.get("muted", ())) == "immediate":
                queue.enqueue(notification["id"], subscriptions)
        def eligible(nid):
            with closing(store.connect()) as db:
                row = db.execute("SELECT * FROM notifications WHERE id=?", (nid,)).fetchone()
            return row is not None and route(dict(row), datetime.now(timezone.utc), push_enabled=True, quiet_start=settings.get("quiet_start", "00:30"), quiet_end=settings.get("quiet_end", "08:00"), muted=settings.get("muted", ())) == "immediate"
        result["delivery"] = queue.drain(push_store, sender, enabled=True, eligible=eligible)
    else:
        result["delivery"] = {"status": "disabled"}
    return result
