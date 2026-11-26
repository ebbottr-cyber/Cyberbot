import os,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from cyberbot.news_memory import summarize,overview,MIN_EVENTS
from cyberbot.news_impact import VERSION

def pair(i,*,category="macro",value="1",source="fixture",basis="publication"):
    t=datetime(2020,1,1,tzinfo=timezone.utc)+timedelta(days=i)
    ref="manual:"+str(i)
    e={"record_key":ref,"event_type":"news","kind":category,"url":"https://example.org/"+str(i),"event_at":t.isoformat(),"recorded_at":t.isoformat()}
    w={"minutes":5,"status":"measured","baseline_at":(t-timedelta(minutes=5)).isoformat(),"endpoint_at":(t+timedelta(minutes=5)).isoformat(),"return_pct":value}
    r={"record_key":ref,"mode":"local_unverified","version":VERSION,"event_at":e["event_at"],"recorded_at":e["recorded_at"],"market":"BIST","symbol":"THYAO.IS","source":source,"interval_minutes":5,basis:[w]}
    return e,r

class NewsMemoryTests(unittest.TestCase):
    def test_sample_gate_and_duplicates(self):
        pairs=[pair(i,value="1" if i%2 else "-1") for i in range(MIN_EVENTS)]
        events,reports=map(list,zip(*pairs))
        small=summarize(reports[:-1],events)
        self.assertIsNone(small["groups"][0]["statistics"])
        d=summarize(reports+[reports[0]],events)
        self.assertEqual(d["groups"][0]["event_count"],MIN_EVENTS)
        self.assertEqual(d["excluded"]["duplicate_windows"],1)
        self.assertEqual(d["groups"][0]["statistics"]["mean_return_pct"],"0.000000")
        self.assertEqual(d["groups"][0]["statistics"]["positive_pct"],"50.000000")
        self.assertFalse(d["prediction_verified"])
    def test_conflicts_and_separation(self):
        e,r=pair(0)
        other={**r,"publication":[{**r["publication"][0],"return_pct":"2"}]}
        self.assertEqual(summarize([r,other],[e])["groups"],[])
        self.assertEqual(summarize([r,other],[e])["excluded"]["conflicting_windows"],2)
        x=summarize([r,{**r,"source":"other"},{**r,"mode":"synthetic"},{**r,"publication":[],"first_observed":r["publication"]}],[e])
        self.assertEqual(len(x["groups"]),3)
        self.assertTrue(all(g["event_count"]==1 for g in x["groups"]))
    def test_overlapping_across_topics(self):
        e,r=pair(0);e2,r2=pair(1,category="company")
        t=datetime.fromisoformat(e["event_at"])+timedelta(minutes=5)
        e2.update(event_at=t.isoformat(),recorded_at=t.isoformat())
        r2.update(event_at=t.isoformat(),recorded_at=t.isoformat(),publication=[{"minutes":5,"status":"measured","baseline_at":(t-timedelta(minutes=5)).isoformat(),"endpoint_at":(t+timedelta(minutes=5)).isoformat(),"return_pct":"2"}])
        d=summarize([r,r2],[e,e2])
        self.assertEqual(d["excluded"]["overlapping_windows"],1)
        self.assertEqual(sum(g["event_count"] for g in d["groups"]),1)
    def test_read_only_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with patch.dict(os.environ,{"CYBERBOT_NEWS_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_NEWS_ENABLED":"0","CYBERBOT_LEARNING_DB":str(p/"learn.sqlite3"),"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":""}):
                self.assertEqual(overview()["status"],"empty")
                self.assertFalse((p/"learn.sqlite3").exists())
            with patch.dict(os.environ,{"CYBERBOT_NEWS_PRICE_RIGHTS_CONFIRMED":"0"}):
                self.assertEqual(overview()["status"],"permission_required")
