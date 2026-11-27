"""Single-operator preferences and morning digest."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from tools.notification_center import CATEGORIES

DEFAULTS = {"quiet_start":"00:30", "quiet_end":"08:00", "muted":[], "push_enabled":False}

class Preferences:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS notification_preferences (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")

    def load(self):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT payload FROM notification_preferences WHERE id=1").fetchone()
        return {**DEFAULTS, **(json.loads(row[0]) if row else {}), "muted": json.loads(row[0]).get("muted", []) if row else []}

    def save(self, settings):
        if set(settings) != set(DEFAULTS):
            raise ValueError("Complete preferences required")
        for field in ("quiet_start", "quiet_end"):
            value = settings[field]
            if not isinstance(value, str) or len(value)!=5 or time.fromisoformat(value).strftime("%H:%M") != value:
                raise ValueError("Invalid local time")
        if type(settings["push_enabled"]) is not bool or not isinstance(settings["muted"], list) or any(c not in CATEGORIES for c in settings["muted"]):
            raise ValueError("Invalid preferences")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO notification_preferences VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (json.dumps(settings),))

def morning_digest(store, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    local = now.astimezone(ZoneInfo("Europe/Istanbul"))
    if local.time() < time(8):
        return False
    end = local.replace(hour=8, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    with closing(store.connect()) as db:
        args = (start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat())
        where = "category='news' AND severity='info' AND event_key NOT LIKE 'digest:%' AND created_at>=? AND created_at<?"
        count = db.execute("SELECT COUNT(*) FROM notifications WHERE "+where,args).fetchone()[0]
        rows = db.execute("SELECT title FROM notifications WHERE "+where+" ORDER BY id DESC LIMIT 20",args).fetchall()
    if not count:
        return False
    return store.publish("digest:"+local.date().isoformat(),"news","info","Günlük haber özeti",str(count)+" haber\n"+"\n".join("- "+r[0][:200] for r in rows),"Cyberbot")
