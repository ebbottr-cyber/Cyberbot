import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from cyberbot.engine import Ledger, PaperError
from cyberbot.lab import experiment

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"test.sqlite3"
        self.ledger=Ledger(self.path)

    def test_start(self):
        s=self.ledger.snapshot()
        self.assertEqual(s["equity"],"10000.00")
        self.assertFalse(s["real_orders"])
        self.assertEqual(len(s["markets"]),4)

    def test_buy_sell_cost(self):
        self.ledger.buy("DEMO-BIST")
        s=self.ledger.snapshot()
        self.assertEqual(s["open_count"],1)
        self.assertLess(Decimal(s["equity"]),Decimal("10000"))
        self.ledger.sell(s["trades"][0]["id"])
        s=self.ledger.snapshot()
        self.assertEqual(s["open_count"],0)
        self.assertLess(Decimal(s["trades"][0]["pnl"]),0)
        with self.assertRaises(PaperError):
            self.ledger.sell(s["trades"][0]["id"])

    def test_duplicate_and_persistence(self):
        self.ledger.buy("DEMO-SOL")
        with self.assertRaises(PaperError):
            self.ledger.buy("DEMO-SOL")
        self.assertEqual(Ledger(self.path).snapshot()["open_count"],1)

    def test_stop(self):
        self.ledger.buy("DEMO-SOL")
        for _ in range(4):
            self.ledger.advance()
        self.assertEqual(self.ledger.snapshot()["trades"][0]["reason"],"stop")

    def test_invalid_and_end(self):
        with self.assertRaises(PaperError):
            self.ledger.buy("BTC")
        for _ in range(9):
            self.ledger.advance()
        with self.assertRaises(PaperError):
            self.ledger.advance()

    def test_lab(self):
        d=experiment("DEMO-BIST")
        self.assertEqual(d["mode"],"synthetic")
        self.assertGreaterEqual(Decimal(d["max_drawdown_pct"]),0)
