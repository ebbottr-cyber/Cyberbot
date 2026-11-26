"""Economic calendar reminders from operator-validated event records."""
from datetime import datetime, timezone, timedelta
import hashlib
import json

def aware(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timezone required")
    return dt.astimezone(timezone.utc)

def emit_reminders(store, events, now=None, lead_minutes=30):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or not 1 <= lead_minutes <= 1440:
        raise ValueError("Invalid reminder configuration")
    result = {"published": 0, "duplicates": 0, "skipped": 0, "invalid": 0}
    for event in events:
        try:
            if event.get("verified") is not True or event.get("cancelled") or event.get("importance") != "high":
                result["skipped"] += 1
                continue
            fields = [event[k] for k in ("id", "title", "source", "market", "scheduled_at")]
            if not all(isinstance(v, str) and v.strip() for v in fields):
                raise ValueError("Missing fields")
            scheduled = aware(event["scheduled_at"])
            if not timedelta(0) < scheduled - now <= timedelta(minutes=lead_minutes):
                result["skipped"] += 1
                continue
            key = "calendar:" + hashlib.sha256(json.dumps([event["source"], event["id"], scheduled.isoformat(), lead_minutes]).encode()).hexdigest()
            added = store.publish(key, "market", "warning", event["title"],
                f'{event["market"]} | Planlanan açıklama: {scheduled.isoformat()} | Kaynak: {event["source"]}. Piyasa etkisi belirsiz.', event["source"])
            result["published" if added else "duplicates"] += 1
        except (KeyError, TypeError, ValueError, AttributeError):
            result["invalid"] += 1
    return result
