"""Read-only handoff from separate notification/news worker databases.

No table creation, delivery, marking read, provider calls or subscription access.
"""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

CATEGORIES = ("news", "market", "data", "system", "risk", "ai", "trade", "github")
LEVELS = ("info", "warning", "critical")
MARKETS = ("BIST", "NASDAQ", "XETRA", "FUTURES", "SOLANA", "GLOBAL")
PRIORITIES = ("low", "medium", "high")
WORKER_MARKETS = tuple("BINANCE_FUTURES" if m == "FUTURES" else m for m in MARKETS)
LIMIT = 50


def stamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Invalid timestamp")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timezone required")
    return dt.astimezone(timezone.utc).isoformat()


def text(value, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("Invalid text")
    return value


def connect(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("BEGIN")
        return db
    except Exception:
        db.close()
        raise


def read_inbox(path=None, category="ALL"):
    base = {"status": "not_configured", "items": [], "window_unread": None,
            "read_only": True, "device_delivery_verified": False, "real_orders": False}
    if category not in ("ALL", *CATEGORIES):
        raise ValueError("Invalid category")
    path = path or os.getenv("CYBERBOT_NOTIFICATION_DB")
    if not path:
        return base
    try:
        if not Path(path).is_file():
            return {**base, "status": "missing"}
        with closing(connect(path)) as db:
            rows = db.execute("""SELECT category,severity,substr(title,1,501),substr(body,1,2001),
                substr(source,1,201),substr(created_at,1,65),read_at IS NULL
                FROM notifications WHERE (?='ALL' OR category=?) ORDER BY id DESC LIMIT ?""",
                (category, category, LIMIT)).fetchall()
        items = []
        for cat, severity, title, body, source, created, unread in rows:
            if cat not in CATEGORIES or severity not in LEVELS:
                raise ValueError("Invalid notification category")
            items.append({"category": cat, "severity": severity, "title": text(title,500),
                          "body": text(body,2000), "source": text(source,200),
                          "created_at": stamp(created), "unread": bool(unread)})
        return {**base, "status": "available" if items else "empty",
                "items": items, "window_unread": sum(x["unread"] for x in items)}
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        return {**base, "status": "unavailable"}


def read_news(path=None, market="ALL"):
    base = {"status": "not_configured", "items": [], "research_only": True,
            "content_verified": False, "impact_verified": False, "orders_enabled": False}
    if market not in ("ALL", *MARKETS):
        raise ValueError("Invalid market")
    path = path or os.getenv("CYBERBOT_RESEARCH_NEWS_DB")
    if not path:
        return base
    try:
        if not Path(path).is_file():
            return {**base, "status": "missing"}
        worker_market = "BINANCE_FUTURES" if market == "FUTURES" else market
        with closing(connect(path)) as db:
            rows = db.execute("""SELECT market,priority,substr(published_at,1,65),
                substr(payload,1,32769) FROM research_news
                WHERE (?='ALL' OR market=? OR market='GLOBAL')
                ORDER BY published_at DESC,event_key LIMIT ?""",(worker_market,worker_market,LIMIT)).fetchall()
        items = []
        for scope, priority, published, payload in rows:
            if scope not in WORKER_MARKETS or priority not in PRIORITIES:
                raise ValueError("Invalid news scope")
            data = json.loads(text(payload,32768))
            if any(data.get(k) is not False for k in ("content_verified","impact_verified","orders_enabled")) or data.get("research_only") is not True:
                raise ValueError("Unexpected news authority")
            if data.get("market") != scope or data.get("priority") != priority or stamp(data["published_at"]) != stamp(published):
                raise ValueError("Inconsistent news record")
            items.append({"market": "FUTURES" if scope == "BINANCE_FUTURES" else scope, "priority": priority,
                          "published_at": stamp(published), "title": text(data["title"],4096),
                          "source": text(data["source"],4096), "summary_tr": text(data.get("summary_tr",""),2000)})
        return {**base, "status": "available" if items else "empty", "items": items}
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return {**base, "status": "unavailable"}
