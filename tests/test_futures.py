import tempfile
import unittest
from pathlib import Path
from decimal import Decimal as D
from cyberbot.futures import Futures
from cyberbot.engine import PaperError
class FuturesTests(unittest.TestCase):
    def test_long_short_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            for side in ("LONG","SHORT"):
                p=Path(tmp)/(side+".sqlite3");f=Futures(p)
                self.assertEqual(f.snapshot()["equity"],"1000.00")
                f.open("BTCUSDT",side)
                with self.assertRaises(PaperError):f.open("ETHUSDT",side)
                f.advance();f.close(1)
                d=Futures(p).snapshot()
                self.assertEqual(d["open_count"],0)
                self.assertEqual(d["equity"],d["cash"])
                self.assertEqual(D(d["pnl"])>0,side=="LONG")
                self.assertFalse(d["real_orders"])
    def test_gap_isolated_margin(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Futures(Path(tmp)/"f.sqlite3")
            for _ in range(6):f.advance()
            f.open("BTCUSDT","LONG");f.advance()
            d=f.snapshot()
            self.assertEqual(d["trades"][0]["reason"],"synthetic_liquidation")
            self.assertGreater(D(d["cash"]),0)
            self.assertEqual(d["open_count"],0)

    def test_equity_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"history.sqlite3";f=Futures(p)
            first=f.snapshot()["equity_history"]
            self.assertEqual(len(first),1)
            self.assertEqual(f.snapshot()["equity_history"],first)
            f.open("BTCUSDT","LONG");f.advance();f.close(1)
            s=Futures(p).snapshot()
            self.assertEqual([x["event"] for x in s["equity_history"]],["initial_observation","open","advance","close"])
            self.assertEqual(s["equity_history"][-1]["equity"],s["equity"])
