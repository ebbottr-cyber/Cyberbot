import tempfile
import unittest
from pathlib import Path
from cyberbot.engine import Ledger

class DashboardTests(unittest.TestCase):
    def test_real_paper_history(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"test.sqlite3"
            l=Ledger(path)
            s=l.snapshot()
            self.assertEqual(len(s["equity_history"]),1)
            self.assertEqual(s["daily_pnl"],"0.00")
            self.assertEqual(s["open_markets"],0)
            l.buy("DEMO-BIST")
            l.advance()
            s=l.snapshot()
            self.assertEqual(len(s["equity_history"]),3)
            self.assertEqual(s["equity_history"][-1]["equity"],s["equity"])
            self.assertEqual(s["open_markets"],1)
            self.assertEqual(len(Ledger(path).snapshot()["equity_history"]),3)
            l.sell(s["trades"][0]["id"])
            self.assertEqual(len(l.snapshot()["equity_history"]),4)
            self.assertFalse(l.snapshot()["real_orders"])
