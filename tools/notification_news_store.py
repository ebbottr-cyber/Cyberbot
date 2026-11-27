"""Structured research-only news storage; no trading or delivery side effects."""
import sqlite3
import json
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlsplit
from tools.notification_news_filter import MARKETS, PRIORITY, matches_news

class NewsStore:
    def __init__(self,path):
        self.path=path
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS research_news (
                event_key TEXT PRIMARY KEY, published_at TEXT NOT NULL,
                market TEXT NOT NULL, priority TEXT NOT NULL, payload TEXT NOT NULL)""")
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS research_news_claims (event_key TEXT PRIMARY KEY)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(research_news_claims)")}
            if "owner" not in columns:
                db.execute("ALTER TABLE research_news_claims ADD COLUMN owner TEXT")
            if "expires" not in columns:
                db.execute("ALTER TABLE research_news_claims ADD COLUMN expires REAL NOT NULL DEFAULT 0")
            db.execute("CREATE TABLE IF NOT EXISTS research_news_delivery (event_key TEXT PRIMARY KEY, done INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0)")
            db.execute("CREATE INDEX IF NOT EXISTS research_news_date ON research_news(published_at DESC)")

    def claim(self, event_key):
        owner = uuid.uuid4().hex
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            if db.execute("SELECT 1 FROM research_news WHERE event_key=?", (event_key,)).fetchone():
                return "duplicate", None
            db.execute("DELETE FROM research_news_claims WHERE event_key=? AND expires<=?", (event_key, now))
            claimed = db.execute("INSERT OR IGNORE INTO research_news_claims (event_key,owner,expires) VALUES (?,?,?)", (event_key,owner,now+900)).rowcount
            return ("claimed", owner) if claimed else ("busy", None)

    def release(self, event_key, owner):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("DELETE FROM research_news_claims WHERE event_key=? AND owner=?", (event_key,owner))

    def save(self,article,*,owner=None):
        required=("event_key","title","source","url","published_at","market","priority")
        for field in required:
            if not isinstance(article.get(field),str) or not article[field].strip() or len(article[field])>4096:
                raise ValueError("Invalid news field")
        if article["market"] not in MARKETS or article["priority"] not in PRIORITY:
            raise ValueError("Invalid market or priority")
        url=urlsplit(article["url"])
        if url.scheme!="https" or not url.hostname or url.username or url.password:
            raise ValueError("HTTPS source required")
        stamp=datetime.fromisoformat(article["published_at"])
        if stamp.tzinfo is None:
            raise ValueError("Timezone required")
        data={k:article[k] for k in required}
        data["published_at"]=stamp.astimezone(timezone.utc).isoformat(timespec="microseconds")
        for field in ("symbols","topics"):
            values=article.get(field,[])
            if not isinstance(values,list) or len(values)>100 or any(not isinstance(v,str) or not v.strip() or len(v)>100 for v in values):
                raise ValueError("Invalid metadata")
            data[field]=values
        summary=article.get("summary_tr","")
        if not isinstance(summary,str) or len(summary)>2000:
            raise ValueError("Invalid summary")
        data.update(summary_tr=summary,direction="unknown",impact_verified=False,content_verified=False,research_only=True,orders_enabled=False)
        with closing(sqlite3.connect(self.path)) as db, db:
            if owner is not None:
                db.execute("BEGIN IMMEDIATE")
                if not db.execute("SELECT 1 FROM research_news_claims WHERE event_key=? AND owner=? AND expires>?", (data["event_key"],owner,time.time())).fetchone():
                    raise RuntimeError("News reservation expired or replaced")
            return bool(db.execute("INSERT OR IGNORE INTO research_news VALUES(?,?,?,?,?)",(data["event_key"],data["published_at"],data["market"],data["priority"],json.dumps(data,ensure_ascii=False))).rowcount)

    def pending_delivery(self, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("Invalid limit")
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("""SELECT n.payload FROM research_news n
                LEFT JOIN research_news_delivery d ON n.event_key=d.event_key
                WHERE COALESCE(d.done,0)=0 AND COALESCE(d.next_at,0)<=?
                ORDER BY n.published_at,n.event_key LIMIT ?""", (time.time(),limit))
            return [json.loads(row[0]) for row in rows]

    def finish_delivery(self, event_key, *, success):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if success:
                db.execute("""INSERT INTO research_news_delivery(event_key,done) VALUES (?,1)
                    ON CONFLICT(event_key) DO UPDATE SET done=1""", (event_key,))
            else:
                row = db.execute("SELECT done,attempts FROM research_news_delivery WHERE event_key=?", (event_key,)).fetchone()
                if row and row[0]:
                    return
                attempts = (row[1] if row else 0)+1
                delay = min(3600, 30 * 2 ** min(attempts-1,7))
                db.execute("""INSERT INTO research_news_delivery(event_key,attempts,next_at) VALUES (?,?,?)
                    ON CONFLICT(event_key) DO UPDATE SET attempts=excluded.attempts,next_at=excluded.next_at""",
                    (event_key,attempts,time.time()+delay))

    def contains(self, event_key):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT 1 FROM research_news WHERE event_key=?", (event_key,)).fetchone() is not None

    def list(self,*,limit=100,**filters):
        if type(limit) is not int or not 1<=limit<=500:
            raise ValueError("Invalid limit")
        result=[]
        with closing(sqlite3.connect(self.path)) as db:
            for (payload,) in db.execute("SELECT payload FROM research_news ORDER BY published_at DESC,event_key"):
                item=json.loads(payload)
                if matches_news(item,**filters):
                    result.append(item)
                    if len(result)>=limit:
                        break
        return result
