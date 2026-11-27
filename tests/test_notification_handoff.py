import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from cyberbot.notification_handoff import read_inbox, read_news


class NotificationHandoffTests(unittest.TestCase):
    def test_inbox_filter_limit_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"inbox.sqlite3"
            self.assertEqual(read_inbox(path)["status"],"missing")
            self.assertFalse(path.exists())
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE notifications(id INTEGER PRIMARY KEY,event_key TEXT,category TEXT,severity TEXT,title TEXT,body TEXT,source TEXT,created_at TEXT,read_at TEXT)")
                db.executemany("INSERT INTO notifications VALUES(?,?,?,?,?,?,?,?,?)",
                    [(i,"secret-key","risk" if i%2 else "ai","warning","title","body","local","2026-11-27T10:00:00+00:00",None if i%2 else "read") for i in range(110)])
            before=path.read_bytes()
            result=read_inbox(path,"risk")
            self.assertEqual(len(result["items"]),50)
            self.assertEqual(result["window_unread"],50)
            self.assertTrue(result["read_only"])
            self.assertFalse(result["device_delivery_verified"])
            self.assertNotIn("secret-key",str(result))
            self.assertEqual(path.read_bytes(),before)

    def test_invalid_database_not_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"wrong.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE other(id INTEGER)")
            before=path.read_bytes()
            self.assertEqual(read_inbox(path)["status"],"unavailable")
            self.assertEqual(read_news(path)["status"],"unavailable")
            self.assertEqual(path.read_bytes(),before)

    def test_research_news_market_mapping_and_authority(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"news.sqlite3"
            stamp="2026-11-27T10:00:00+00:00"
            def article(market):
                return {"market":market,"priority":"high","published_at":stamp,
                        "title":"Research","source":"local","summary_tr":"summary",
                        "url":"https://example.invalid/private","content_verified":False,
                        "impact_verified":False,"orders_enabled":False,"research_only":True}
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE research_news(event_key TEXT PRIMARY KEY,published_at TEXT,market TEXT,priority TEXT,payload TEXT)")
                for m in ("BINANCE_FUTURES","GLOBAL","BIST"):
                    db.execute("INSERT INTO research_news VALUES(?,?,?,?,?)",(m,stamp,m,"high",json.dumps(article(m))))
            before=path.read_bytes()
            result=read_news(path,"FUTURES")
            self.assertEqual({r["market"] for r in result["items"]},{"FUTURES","GLOBAL"})
            self.assertFalse(result["impact_verified"])
            self.assertNotIn("example.invalid",str(result))
            self.assertEqual(path.read_bytes(),before)
            with closing(sqlite3.connect(path)) as db, db:
                data=article("BINANCE_FUTURES");data["orders_enabled"]=True
                db.execute("UPDATE research_news SET payload=? WHERE market='BINANCE_FUTURES'",(json.dumps(data),))
            self.assertEqual(read_news(path,"FUTURES")["status"],"unavailable")
