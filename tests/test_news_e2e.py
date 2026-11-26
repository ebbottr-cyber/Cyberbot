import io,json,os,tempfile,unittest,zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from cyberbot.api import app
from cyberbot.news import save,normalize_url
from cyberbot.news_graph import find_record
from cyberbot.news_impact import run_local

class NewsE2E(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        env={"CYBERBOT_DB":str(self.root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(self.root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(self.root/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_TAILSCALE_ENABLED":"0","CYBERBOT_NEWS_ENABLED":"0","CYBERBOT_NEWS_PRICE_RIGHTS_CONFIRMED":"0","CYBERBOT_LOCAL_LLM_ENABLED":"0","CYBERBOT_NEWS_LLM_ENABLED":"0"}
        p=patch.dict(os.environ,env);p.start();self.addCleanup(p.stop)
        self.c=TestClient(app,base_url="http://127.0.0.1",client=("127.0.0.1",12345));self.addCleanup(self.c.close)
        self.headers={"X-Cyberbot-Paper":"1"}
    def get(self,path):
        r=self.c.get(path);self.assertEqual(r.status_code,200,r.text[:300]);self.assertEqual(r.headers["cache-control"],"no-store");return r.json()
    def test_flow(self):
        now=datetime.now(timezone.utc)
        item={"market":"BIST","kind":"company","event_type":"news","url":"https://example.org/fixture","event_at":(now-timedelta(days=2)).isoformat(),"label":"Test fixture"}
        with patch("cyberbot.news_feed.fetch",side_effect=AssertionError("unexpected network")):
            for path in ("/api/news","/api/news/rss","/api/news/graph","/api/news/impact","/api/news/memory","/api/news/overview","/api/knowledge"):self.get(path)
            self.assertFalse((self.root/"learn.sqlite3").exists())
            self.assertEqual(self.c.post("/api/news",json=item).status_code,403)
            self.assertEqual(self.c.post("/api/news",json=item,headers={**self.headers,"Origin":"https://evil.example"}).status_code,403)
            r=self.c.post("/api/news",json=item,headers=self.headers);self.assertEqual(r.status_code,200,r.text);key="manual:"+r.json()["id"]
            body={"record_key":key,"market":"BIST","symbol":"THYAO.IS","evidence_url":"https://example.org/fixture"}
            self.assertEqual(self.c.post("/api/news/graph/link",json=body,headers=self.headers).status_code,200)
            a=self.get("/api/news/agents/"+key);self.assertEqual(len(a["agents"]),7);self.assertIsNone(a["direction_prediction"])
            self.assertEqual(self.c.post("/api/news/agents/"+key+"/checklist",headers=self.headers).status_code,403)
            self.assertEqual(self.c.post("/api/news/rss/fed",headers=self.headers).status_code,409)
            self.assertEqual(self.get("/api/news/overview")["visible_news_count"],1)
            before=(self.root/"learn.sqlite3").read_bytes()
            z=self.c.get("/api/knowledge/vault.zip")
            self.assertEqual(z.status_code,200)
            with zipfile.ZipFile(io.BytesIO(z.content)) as archive:self.assertIn("Haberler.canvas",archive.namelist())
            self.assertEqual((self.root/"learn.sqlite3").read_bytes(),before)
            self.assertFalse((self.root/"paper.sqlite3").exists())
    def test_calendar_crowding_and_url(self):
        now=datetime.now(timezone.utc)
        base={"market":"BIST","kind":"macro","url":"https://example.org/event","label":"fixture"}
        key="manual:"+save({**base,"event_type":"news","event_at":(now-timedelta(days=1)).isoformat()})["id"]
        for i in range(101):save({**base,"event_type":"calendar","event_at":(now+timedelta(days=i+1)).isoformat()})
        self.assertIsNotNone(find_record(key))
        self.assertEqual(self.get("/api/news/agents/"+key)["event_type"],"news")
        self.assertEqual(self.get("/api/news/overview")["visible_news_count"],1)
        for u in ("https://@example.org","https://example.org%2f.evil.org","javascript:alert(1)"):
            with self.assertRaises(ValueError):normalize_url(u)
