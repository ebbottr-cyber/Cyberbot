"""Structured research-only news storage; no trading or delivery side effects."""
import sqlite3
import json
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
            db.execute("CREATE INDEX IF NOT EXISTS research_news_date ON research_news(published_at DESC)")

    def save(self,article):
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
            return bool(db.execute("INSERT OR IGNORE INTO research_news VALUES(?,?,?,?,?)",(data["event_key"],data["published_at"],data["market"],data["priority"],json.dumps(data,ensure_ascii=False))).rowcount)

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
