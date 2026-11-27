"""Synthetic conditional evidence tests."""
from datetime import datetime,timedelta,timezone
import unittest
from cyberbot.conditional_strategy_review import review


NOW=datetime(2020,2,1,tzinfo=timezone.utc)


def decision(at, i=0):
    scope={"policy":"pilot-shadow-2","market":"FUTURES","symbol":"BTCUSDT",
           "source":"test","venue":None,"fx_source":None,"pool":None}
    return {"id":str(i),"as_of":at.isoformat(),"version":"pilot-shadow-2",
            "market":"FUTURES","symbol":"BTCUSDT","source":"test","scope":scope,
            "mode":"shadow_only","actual_action":"HOLD","hypothetical_action":"LONG",
            "candidate":"trend","paper_order_created":False,"real_orders":False,
            "blockers":["automatic_entry_disabled"],
            "regime_diagnostic":{"version":"observed-regime-diagnostic-1",
                "market":"FUTURES","interval":"1m","observations":21,
                "direction":"bull","volatility":"normal",
                "liquidity":{"status":"asserted_threshold_met"},
                "real_orders":False,"execution_verified":False}}


def rows(stress="0.2"):
    result=[]
    for i in range(36):
        start=NOW-timedelta(days=12-i//3,minutes=20-(i%3)*7)
        d=decision(start,i+1)
        o={"version":"shadow-outcome-2","decision_id":d["id"],
           "decision_at":d["as_of"],"decision_version":d["version"],
           "scope":d["scope"],"market":d["market"],"symbol":d["symbol"],
           "source":d["source"],"candidate":"trend","direction":"LONG",
           "covered_until":(start+timedelta(seconds=360)).isoformat(),
           "entry_at":(start+timedelta(seconds=10)).isoformat(),
           "exit_at":(start+timedelta(seconds=310)).isoformat(),
           "execution_verified":False,"status":"measured","net_pct":"0.5",
           "double_cost_pct":stress}
        result.append((d,o,o["covered_until"]))
    return result


class ConditionalReviewTests(unittest.TestCase):
    def test_positive_review_never_orders(self):
        r=review(decision(NOW),rows(),NOW)
        self.assertEqual(r["status"],"REVIEW_ONLY")
        self.assertEqual(r["candidate"],"trend")
        self.assertEqual(r["action"],"HOLD")
        self.assertFalse(r["real_orders"])

    def test_stress_cost_rejects(self):
        r=review(decision(NOW),rows("-0.1"),NOW)
        self.assertIsNone(r["candidate"])

    def test_sparse(self):
        self.assertEqual(review(decision(NOW),rows()[:3],NOW)["status"],"INSUFFICIENT_EVIDENCE")

    def test_risk(self):
        d=decision(NOW)
        d["regime_diagnostic"]["volatility"]="high"
        self.assertEqual(review(d,rows(),NOW)["status"],"RISK_CONTEXT_HOLD")

    def test_other_symbol(self):
        d=decision(NOW)
        d["symbol"]=d["scope"]["symbol"]="ETHUSDT"
        self.assertIsNone(review(d,rows(),NOW)["candidate"])

    def test_duplicate(self):
        data=rows()
        data.insert(1,data[0])
        self.assertEqual(review(decision(NOW),data,NOW)["status"],"DATA_REVIEW_REQUIRED")

    def test_existing_gate(self):
        d=decision(NOW)
        d["blockers"].append("kill_switch")
        self.assertEqual(review(d,rows(),NOW)["status"],"EXISTING_GATE_HOLD")

    def test_no_alternative_invention(self):
        d=decision(NOW)
        d["candidate"]="momentum"
        self.assertIsNone(review(d,rows(),NOW)["candidate"])


if __name__=="__main__":
    unittest.main()
