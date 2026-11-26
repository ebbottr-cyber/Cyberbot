"""Local research notification store; no trading or network side effects."""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

CATEGORIES = {"news", "market", "data", "system", "risk", "ai", "trade", "github"}
LEVELS = {"info", "warning", "critical"}

class NotificationStore:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL, severity TEXT NOT NULL,
                title TEXT NOT NULL, body TEXT NOT NULL, source TEXT NOT NULL,
                created_at TEXT NOT NULL, read_at TEXT)""")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def publish(self, event_key, category, severity, title, body, source):
        if category not in CATEGORIES or severity not in LEVELS:
            raise ValueError("Invalid category or severity")
        if not all(isinstance(v, str) and v.strip() for v in
                   (event_key, title, body, source)):
            raise ValueError("Required text missing")
        with closing(self.connect()) as db, db:
            cur = db.execute("""INSERT INTO notifications
                (event_key, category, severity, title, body, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event_key) DO NOTHING""",
                (event_key, category, severity, title, body, source,
                 datetime.now(timezone.utc).isoformat()))
            return cur.rowcount == 1

    def list(self, category=None, unread=False, limit=100):
        if category is not None and category not in CATEGORIES:
            raise ValueError("Invalid category")
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("Invalid limit")
        with closing(self.connect()) as db:
            rows = db.execute("""SELECT * FROM notifications
                WHERE (? IS NULL OR category = ?) AND (? = 0 OR read_at IS NULL)
                ORDER BY id DESC LIMIT ?""", (category, category, int(unread), limit))
            return [dict(row) for row in rows]

    def mark_read(self, notification_id):
        with closing(self.connect()) as db, db:
            return db.execute("""UPDATE notifications SET read_at = ?
                WHERE id = ? AND read_at IS NULL""",
                (datetime.now(timezone.utc).isoformat(), notification_id)).rowcount == 1
