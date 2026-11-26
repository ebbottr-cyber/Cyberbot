import unittest,os,tempfile,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from cyberbot.news_impact import measure,demo,run_local,recent

class NewsImpactTests(unittest.TestCase):
    def test_windows(self):
        start=datetime(2020,1,1,tzinfo=timezone.utc)
        prices=[{"closed_at":(start+timedelta(minutes=5*i)).isoformat(),"close":str(100+i)} for i in range(300)]
        event=(start+timedelta(minutes=6)).isoformat()
        observed=(start+timedelta(minutes=11)).isoformat()
        d=measure(event,observed,prices,5,now=start+timedelta(days=2))
        self.assertEqual(d["publication"][0]["baseline_at"],(start+timedelta(minutes=5)).isoformat())
        self.assertEqual(d["publication"][0]["endpoint_at"],(start+timedelta(minutes=15)).isoformat())
        self.assertEqual(d["publication"][0]["return_pct"],"1.980198")
        self.assertNotEqual(d["publication"][0],d["first_observed"][0])
        self.assertEqual(d["publication"][-1]["status"],"measured")
        gap=measure(event,observed,prices[:2]+prices[3:],5,now=start+timedelta(days=2))
        self.assertEqual(gap["publication"][0]["status"],"missing_observations")
        self.assertIsNone(gap["publication"][0]["return_pct"])
        self.assertFalse(d["causal_impact_verified"])
    def test_pending_and_no_future(self):
        t=datetime(2020,1,1,tzinfo=timezone.utc);a=t+timedelta(minutes=5)
        prices=[{"closed_at":x.isoformat(),"close":"100"} for x in (t,a)]
        d=measure(a.isoformat(),a.isoformat(),prices,5,now=a)
        self.assertEqual(d["publication"][0]["status"],"pending")
        with self.assertRaises(ValueError):measure(a.isoformat(),a.isoformat(),prices,5,now=t)
    def test_demo_and_permission(self):
        self.assertEqual(demo()["mode"],"synthetic")
        with patch.dict(os.environ,{"CYBERBOT_NEWS_PRICE_RIGHTS_CONFIRMED":"0"}):
            with self.assertRaises(ValueError):run_local("not-present.json","x","BIST","THYAO.IS")
            self.assertEqual(recent(),[])
