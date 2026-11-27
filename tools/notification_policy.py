"""Research notification routing; no delivery or trading side effects."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from tools.notification_center import CATEGORIES, LEVELS

def route(notification, now=None, *, timezone_name="Europe/Istanbul",
          quiet_start="00:30", quiet_end="08:00", muted=(), push_enabled=False):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    category, severity = notification["category"], notification["severity"]
    if category not in CATEGORIES or severity not in LEVELS:
        raise ValueError("Invalid notification")
    local = now.astimezone(ZoneInfo(timezone_name)).time().replace(tzinfo=None)
    start, end = time.fromisoformat(quiet_start), time.fromisoformat(quiet_end)
    if start.tzinfo or end.tzinfo:
        raise ValueError("Quiet hours must be local")
    quiet = start <= local < end if start < end else (local >= start or local < end) if start > end else False
    if not push_enabled or category in muted:
        return "inbox"
    if severity == "critical":
        return "immediate"
    if category == "news" and severity == "info" and not notification.get("event_key", "").startswith("digest:"):
        return "digest"
    return "deferred" if quiet else "immediate"

def publish_digest(store, notifications, now=None, timezone_name="Europe/Istanbul"):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    local = now.astimezone(ZoneInfo(timezone_name))
    items = [n for n in notifications if n["category"] == "news" and n["severity"] == "info"
             and datetime.fromisoformat(n["created_at"]).astimezone(ZoneInfo(timezone_name)).date() == local.date()
             and not n["event_key"].startswith("digest:")]
    if not items:
        return False
    titles = "\n".join("- " + n["title"][:200] for n in items[:20])
    return store.publish("digest:" + local.date().isoformat(), "news", "info",
                         "Günlük haber özeti", f"{len(items)} haber\n{titles}", "Cyberbot")
