"""Offline portfolio risk regression tests."""
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from tools.fund_etf_risk import assess


class RiskTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name)/"prices.sqlite3"
        self.holdings = [
            dict(market="TEFAS",symbol="AAA",currency="TRY",source="fixture",group="equity",units=1),
            dict(market="ETF",symbol="BBB",currency="TRY",source="fixture",group="equity",units=1)]
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE fund_prices (market TEXT,symbol TEXT,currency TEXT,source TEXT,session TEXT,close TEXT)")
            for h in self.holdings:
                for i in range(90):
                    day = date.today()-timedelta(days=90-i)
                    price = (100+i+(i%4)*.5)*(2 if h["market"]=="ETF" else 1)
                    db.execute("INSERT INTO fund_prices VALUES (?,?,?,?,?,?)",
                               (h["market"],h["symbol"],h["currency"],h["source"],day.isoformat(),str(price)))

    def test_correlated_assets_and_limits(self):
        result = assess(self.db,self.holdings,currency="TRY")
        self.assertEqual(result["status"],"review_required")
        self.assertAlmostEqual(result["correlation_matrix"][0][1],1)
        self.assertAlmostEqual(sum(p["weight"] for p in result["positions"]),1)
        self.assertTrue({"position_limit","group_limit","correlation_review","cash_floor"} <=
                        {a["code"] for a in result["alerts"]})
        self.assertFalse(result["real_orders"])

    def test_cash_and_shock(self):
        result = assess(self.db,self.holdings,currency="TRY",cash=1000)
        self.assertAlmostEqual(result["cash_weight"]+sum(p["weight"] for p in result["positions"]),1)
        self.assertAlmostEqual(result["hypothetical_shock_loss"],.1*(result["equity"]-1000))

    def test_mixed_currency(self):
        self.holdings[1]["currency"]="USD"
        with self.assertRaises(ValueError):
            assess(self.db,self.holdings,currency="TRY")

    def test_duplicate_asset(self):
        with self.assertRaises(ValueError):
            assess(self.db,self.holdings+[dict(self.holdings[0],source="other")],currency="TRY")

    def test_stale_and_insufficient_history(self):
        self.assertEqual(assess(self.db,self.holdings,currency="TRY",max_age_days=0)["reason"],
                         "missing_or_stale_price")
        self.assertEqual(assess(self.db,self.holdings,currency="TRY",min_observations=100)["reason"],
                         "insufficient_common_history")


if __name__ == "__main__":
    unittest.main()
