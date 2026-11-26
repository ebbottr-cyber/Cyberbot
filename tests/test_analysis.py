import unittest
from cyberbot.analysis import demo_review,review

class AnalysisTests(unittest.TestCase):
    def test_demo_no_future(self):
        r=demo_review("DEMO-BIST",2)
        self.assertEqual(r["evidence"]["count"],3)
        self.assertEqual(r["agents"][0]["status"],"veri_yetersiz")
        self.assertFalse(r["real_orders"])
        self.assertFalse(r["llm_enabled"])

    def test_calculation(self):
        r=review("X",[{"close":x} for x in [10,12,9,11,13]],mode="historical_unverified",source="fixture")
        self.assertEqual(r["agents"][0]["metrics"]["ortalama"],"11.00")
        self.assertEqual(r["agents"][3]["metrics"]["maks_dusus_pct"],"25.00")
        self.assertEqual(r["agents"][4]["status"],"veri_yok")
        self.assertEqual(r["verdict"],"research_only")

    def test_no_evidence(self):
        r=review("X",[],mode="historical_unverified",source="fixture")
        self.assertTrue(all(a["status"] in ("veri_yetersiz","veri_yok","arastirma") for a in r["agents"]))
        self.assertFalse(r["paper_orders_enabled"])
