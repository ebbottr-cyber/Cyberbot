"""Synthetic tests; no external data and no orders."""
from datetime import date,timedelta
from decimal import Decimal as D
import unittest
from tools.local_research.equity_parameter_review import evaluate


def bars():
    return [{"session":(date(2020,1,1)+timedelta(days=i)).isoformat(),
             "open":100,"high":101,"low":99,"close":100,"volume":100}
            for i in range(240)]


class OptimizerTests(unittest.TestCase):
    def test_frozen_final_and_bounded_grid(self):
        calls=[]
        def simulator(data,name,window,start,end,**cost):
            self.assertEqual(len(data),end)
            calls.append((name,window,start,end))
            # All pass, deterministic ties; discovery selects three.
            return {"return":D(".03"),"drawdown":D(".01"),"closed":6}
        r=evaluate(bars(),market="BIST",symbol="TEST.IS",simulator=simulator)
        self.assertEqual(r["configurations"],15)
        self.assertEqual(len(calls),38)
        self.assertEqual(sum(end==240 for _,_,_,end in calls),2)
        self.assertEqual(r["status"],"REVIEW_ONLY")
        self.assertFalse(r["automatic_promotion"])
        self.assertFalse(r["real_orders"])

    def test_no_runner_up_after_final_failure(self):
        calls=[]
        def simulator(data,name,window,start,end,**cost):
            calls.append(end)
            return {"return":D("-.01") if end==240 else D(".03"),
                    "drawdown":D(".01"),"closed":6}
        r=evaluate(bars(),market="NASDAQ",symbol="TEST",simulator=simulator)
        self.assertEqual(r["status"],"FINAL_FAILED")
        self.assertEqual(calls.count(240),2)

    def test_no_candidate(self):
        r=evaluate(bars(),market="XETRA",symbol="TEST.DE")
        self.assertEqual(r["status"],"NO_CANDIDATE")
        self.assertIsNone(r["final"])

    def test_bad_volume(self):
        data=bars()
        data[60]["volume"]=0
        with self.assertRaises(ValueError):
            evaluate(data,market="BIST",symbol="TEST.IS")

    def test_duplicate_session(self):
        data=bars()
        data[60]["session"]=data[59]["session"]
        with self.assertRaises(ValueError):
            evaluate(data,market="BIST",symbol="TEST.IS")

    def test_wrong_market(self):
        with self.assertRaises(ValueError):
            evaluate(bars(),market="FUTURES",symbol="BTCUSDT")


if __name__=="__main__":
    unittest.main()
