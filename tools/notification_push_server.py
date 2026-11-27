"""Single-operator push adapter. Explicit activation and external VAPID secret required."""
import sqlite3
import json
import base64
from contextlib import closing
from urllib.parse import urlsplit

def validate(subscription):
    endpoint = subscription["endpoint"]
    url = urlsplit(endpoint)
    if url.scheme != "https" or url.username or url.password or url.port not in (None, 443) or url.fragment:
        raise ValueError("Invalid push endpoint")
    if url.hostname not in {"web.push.apple.com", "fcm.googleapis.com", "updates.push.services.mozilla.com"}:
        raise ValueError("Unsupported push provider")
    if len(endpoint) > 4096 or not url.path.strip("/"):
        raise ValueError("Invalid endpoint")
    keys = subscription["keys"]
    for name, length in (("p256dh", 65), ("auth", 16)):
        value = keys[name]
        if not isinstance(value, str) or len(value) > 128:
            raise ValueError("Invalid subscription key")
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        if len(decoded) != length or (name == "p256dh" and decoded[0] != 4):
            raise ValueError("Invalid subscription key")
    return {"endpoint": endpoint, "keys": {k: keys[k] for k in ("p256dh", "auth")}}

class PushStore:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS push_subscriptions (endpoint TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def save(self, subscription):
        sub = validate(subscription)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO push_subscriptions VALUES (?, ?) ON CONFLICT(endpoint) DO UPDATE SET payload=excluded.payload", (sub["endpoint"], json.dumps(sub)))

    def remove(self, endpoint):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))

    def subscriptions(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM push_subscriptions")]

def deliver(store, subscription, notification_id, sender, *, enabled=False):
    """Sender must enforce HTTPS, no redirects, timeout, and use server-held VAPID keys.
    Returns retry classification; caller owns persistent retry scheduling.
    """
    if not enabled:
        return "disabled"
    sub = validate(subscription)
    # Keep private trading details off lock screens by default.
    payload = json.dumps({"id": str(notification_id), "title": "Cyberbot", "body": "Yeni bildiriminiz var."})
    status = sender(sub, payload)
    if 200 <= status < 300:
        return "accepted"
    if status in (404, 410):
        store.remove(sub["endpoint"])
        return "expired"
    if status in (408, 429) or 500 <= status < 600:
        return "retry"
    return "failed"
