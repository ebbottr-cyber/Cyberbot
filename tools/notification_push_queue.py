"""Persistent delivery queue; explicit single-worker activation required."""
import sqlite3
import time
from contextlib import closing
from tools.notification_push_server import deliver

class PushQueue:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS push_queue (
                notification_id INTEGER NOT NULL, endpoint TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                due REAL NOT NULL, PRIMARY KEY(notification_id, endpoint))""")

    def enqueue(self, notification_id, subscriptions):
        with closing(sqlite3.connect(self.path)) as db, db:
            for sub in subscriptions:
                db.execute("INSERT OR IGNORE INTO push_queue(notification_id,endpoint,due) VALUES (?,?,?)",
                           (notification_id, sub["endpoint"], time.time()))

    def drain(self, store, sender, *, enabled=False, limit=20):
        if not enabled:
            return {"status": "disabled"}
        if not 1 <= limit <= 100:
            raise ValueError("Invalid batch limit")
        subscriptions = {s["endpoint"]: s for s in store.subscriptions()}
        counts = {}
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("SELECT notification_id,endpoint,attempts FROM push_queue WHERE state='pending' AND due<=? ORDER BY due LIMIT ?", (time.time(), limit)).fetchall()
            for nid, endpoint, attempts in rows:
                # Atomic lease prevents concurrent workers claiming the same row.
                with db:
                    claimed = db.execute("UPDATE push_queue SET due=?,attempts=attempts+1 WHERE notification_id=? AND endpoint=? AND state='pending' AND due<=? AND attempts=?", (time.time()+300,nid,endpoint,time.time(),attempts)).rowcount
                if not claimed:
                    continue
                if attempts >= 5:
                    status = "failed"
                elif endpoint not in subscriptions:
                    status = "expired"
                else:
                    try:
                        status = deliver(store, subscriptions[endpoint], nid, sender, enabled=True)
                    except Exception:
                        status = "retry"
                state = "pending" if status == "retry" and attempts+1 < 5 else ("failed" if status == "retry" else status)
                with db:
                    db.execute("UPDATE push_queue SET state=?,due=? WHERE notification_id=? AND endpoint=? AND attempts=?", (state,time.time()+min(3600,30*2**min(attempts,7)),nid,endpoint,attempts+1))
                counts[state] = counts.get(state,0)+1
        return counts
