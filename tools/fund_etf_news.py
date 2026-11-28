"""Offline disclosure inbox; no scraping, push delivery or trading."""
import sqlite3
from contextlib import closing
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit

def ingest(database, items):
    rows=[]
    for item in items:
        source=item["source"].strip()
        market=item["market"]
        title=item["title"].strip()
        url=item["url"]
        parsed=urlsplit(url)
        published=datetime.fromisoformat(item["published"].replace("Z","+00:00"))
        if market not in ("TEFAS","ETF") or not source or not title or parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or published.tzinfo is None or published>datetime.now(timezone.utc):
            raise ValueError("Invalid disclosure")
        if source=="KAP" and parsed.hostname not in ("kap.org.tr","www.kap.org.tr"):
            raise ValueError("Invalid KAP origin")
        stamp=published.astimezone(timezone.utc).isoformat()
        symbol=item["symbol"].strip().upper()
        if not symbol:
            raise ValueError("Missing symbol")
        key=hashlib.sha256(repr((market,symbol,source,url,stamp)).encode()).hexdigest()
        rows.append((key,market,symbol,source,title[:500],url,stamp))
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS fund_news (id TEXT PRIMARY KEY,market TEXT,symbol TEXT,source TEXT,title TEXT,url TEXT,published TEXT)")
        before=db.total_changes
        db.executemany("INSERT INTO fund_news VALUES (?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",rows)
        return db.total_changes-before

def inbox(database, market, *, limit=50, notifications_enabled=False):
    if market not in ("TEFAS","ETF") or not isinstance(limit,int) or not 1<=limit<=200:
        raise ValueError("Invalid inbox query")
    with closing(sqlite3.connect(database)) as db, db:
        db.row_factory=sqlite3.Row
        rows=db.execute("SELECT * FROM fund_news WHERE market=? ORDER BY published DESC,id LIMIT ?",(market,limit)).fetchall()
    return {"items":[{**dict(r),"source_verified":False,"review_event":notifications_enabled is True,"real_orders":False} for r in rows],"delivery_enabled":False}
