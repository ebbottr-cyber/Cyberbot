import unittest
from tools.dexterm_candidate_review import review

MINT="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

def report(values):
    return {"source":"dexterm_screener_query","status":"diagnostic_complete",
            "source_error_count":0,"candidate_count":1,
            "candidates":[{"mint":MINT,"reported":values}],
            "security_verified":False,"live_data_verified":False,
            "pilot_applied":False,"real_orders":False}

class DexTermCandidateReviewTests(unittest.TestCase):
    def test_historical_shortlist_not_live_authorization(self):
        d=review(report({"priceUsd":0.1,"liquidityUsd":100000,"fetchedAt":100000,"ageSec":3}),now_ms=200000)
        self.assertEqual(d["shortlist_mints"],[MINT])
        self.assertFalse(d["candidates"][0]["fresh_at_review"])
        self.assertFalse(d["candidates"][0]["trade_eligible"])
        self.assertFalse(d["security_verified"])
    def test_missing_and_low_liquidity_rejected(self):
        d=review(report({"liquidityUsd":99999}),now_ms=200000)
        self.assertEqual(d["shortlist_count"],0)
        self.assertEqual(len(d["candidates"][0]["reasons"]),4)
    def test_partial_report_and_future_timestamp(self):
        r=report({"priceUsd":1,"liquidityUsd":100000,"fetchedAt":200001,"ageSec":0})
        self.assertEqual(review(r,now_ms=200000)["shortlist_count"],0)
        r["status"]="diagnostic_partial"
        with self.assertRaises(ValueError):review(r,now_ms=200000)
