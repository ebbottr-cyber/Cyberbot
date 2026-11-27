"""Synthetic regime diagnostics: never call providers or place orders."""
import unittest
from datetime import datetime, timezone, timedelta
from cyberbot.observed_regime import diagnose, liquidity


class ObservedRegimeTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2020,1,1,tzinfo=timezone.utc)
        self.quote={"source_at":self.now.isoformat(),"bid":"100","ask":"100.1",
                    "bid_depth_usdt":"200","ask_depth_usdt":"200"}

    def test_direction_separate_from_volatility(self):
        for prices,expected in [([100*(1.001)**i for i in range(21)],"bull"),
                                ([100*(.999)**i for i in range(21)],"bear"),
                                ([100]*21,"sideways")]:
            d=diagnose("FUTURES",prices,self.quote,self.now)
            self.assertEqual(d["direction"],expected)
            self.assertEqual(d["volatility"],"normal")
            self.assertFalse(d["automatic_strategy_switching"])

    def test_volatile_sideways(self):
        d=diagnose("FUTURES",[100 if i%2==0 else 102 for i in range(21)],self.quote,self.now)
        self.assertEqual(d["direction"],"sideways")
        self.assertEqual(d["volatility"],"high")

    def test_book_constraints(self):
        self.assertEqual(liquidity("FUTURES",self.quote,self.now)["status"],"asserted_threshold_met")
        q={**self.quote,"ask":"101","bid_depth_usdt":"50"}
        d=liquidity("FUTURES",q,self.now)
        self.assertEqual(d["status"],"constrained")
        self.assertEqual(set(d["reasons"]),{"low_asserted_depth","wide_spread"})

    def test_unknown_book(self):
        for q in [{**self.quote,"source_at":(self.now-timedelta(seconds=31)).isoformat()},
                  {**self.quote,"bid_depth_usdt":"NaN"},
                  {k:v for k,v in self.quote.items() if k!="ask_depth_usdt"}]:
            self.assertEqual(liquidity("FUTURES",q,self.now)["status"],"unknown")

    def test_equity_venue_and_size(self):
        q={**self.quote,"venue":"XNYS","bid_size":"10","ask_size":"10"}
        self.assertEqual(liquidity("NASDAQ",q,self.now)["status"],"unknown")
        d=liquidity("NASDAQ",{**q,"venue":"XNAS"},self.now)
        self.assertEqual(d["depth_unit"],"shares")
        self.assertEqual(d["status"],"asserted_threshold_met")

    def test_solana_pool_is_not_depth(self):
        q={**self.quote,"liquidity_usd":"200000"}
        self.assertEqual(liquidity("SOLANA",q,self.now)["status"],"unknown")
        q.update(bid_depth_usd="50",ask_depth_usd="200")
        self.assertEqual(liquidity("SOLANA",q,self.now)["status"],"constrained")
        q["ask_depth_usd"]="300000"
        self.assertEqual(liquidity("SOLANA",q,self.now)["status"],"unknown")

    def test_invalid_context(self):
        for p in [[100]*20,[100]*20+[float("nan")]]:
            with self.assertRaises(ValueError):
                diagnose("FUTURES",p,self.quote,self.now)


if __name__=="__main__":
    unittest.main()
