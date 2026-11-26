"""Explicit service cycle; no automatic startup or trading integration."""
from datetime import datetime, timezone
from tools.notification_news_sources import poll_source
from tools.notification_calendar import emit_reminders
from tools.notification_policy import route

def run_cycle(store, push_store, queue, *, events=(), sources=(), user_agent=None,
              sender=None, enabled=False, push_enabled=False, now=None):
    if not enabled:
        return {"status": "disabled"}
    now = now or datetime.now(timezone.utc)
    result = {"status": "ok", "sources": {}}
    for source in sources:
        try:
            result["sources"][source] = poll_source(store, source, enabled=True, user_agent=user_agent)
        except Exception as exc:
            result["sources"][source] = {"status": "error", "type": type(exc).__name__}
    result["calendar"] = emit_reminders(store, events, now)
    if push_enabled and sender is not None:
        subscriptions = push_store.subscriptions()
        # Bounded initial integration; durable cursor and digest scheduling remain separate.
        for notification in store.list(limit=500, unread=True):
            if route(notification, now, push_enabled=True) == "immediate":
                queue.enqueue(notification["id"], subscriptions)
        result["delivery"] = queue.drain(push_store, sender, enabled=True)
    else:
        result["delivery"] = {"status": "disabled"}
    return result
