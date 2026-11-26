import tempfile,unittest,os
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot.news_overview import assemble,snapshot
from cyberbot.news import save
class NewsOverviewTests(unittest.TestCase):
    def test_states(self):
        now=datetime.now(timezone.utc)
        stamp=(now-timedelta(minutes=40)).isoformat()
        feed={"id":"fed","name":"FED","enabled":True,"status":"ok","last_success":stamp}
        x={"id":"x","label":"Example","url":"https://example.org/a","market":"NASDAQ","source":"FED","event_type":"news","event_at":stamp,"kind":"macro","category":"monetary_policy"}
        d=assemble([x],[],{"feeds":[feed],"items":[x]},{"status":"empty","groups":[]},now=now)
        self.assertEqual(d["visible_news_count"],1)
        self.assertEqual(d["high_priority_count"],1)
        self.assertEqual(d["feeds"][0]["dashboard_status"],"stale")
        self.assertFalse(d["live_feed_verified"])
        self.assertFalse(d["real_orders"])
    def test_calendar_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with patch.dict(os.environ,{"CYBERBOT_LEARNING_DB":str(p/"learning.sqlite3"),"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_NEWS_ENABLED":"0","CYBERBOT_NEWS_PRICE_RIGHTS_CONFIRMED":"0"}):
                self.assertEqual(snapshot()["upcoming"],[])
                self.assertFalse((p/"learning.sqlite3").exists())
                now=datetime.now(timezone.utc)
                for days in (20,3,1/24):
                    save({"market":"BIST","kind":"macro","event_type":"calendar","url":"https://example.org/event","event_at":(now+timedelta(days=days)).isoformat(),"label":"Test calendar"})
                before=(p/"learning.sqlite3").read_bytes()
                d=snapshot()
                self.assertEqual(d["upcoming_count"],2)
                self.assertTrue(d["upcoming"][0]["within_24h"])
                self.assertEqual(d["visible_news_count"],0)
                self.assertEqual((p/"learning.sqlite3").read_bytes(),before)
                self.assertFalse((p/"paper.sqlite3").exists())
