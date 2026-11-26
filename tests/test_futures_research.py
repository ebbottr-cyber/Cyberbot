import unittest
from decimal import Decimal as D
from cyberbot.futures_research import evaluate,rows_for,simulate

class FuturesResearchTests(unittest.TestCase):
    def test_causal_selection(self):
        a=rows_for("BTCUSDT")
        b=a[:-60]+[{"open":"100","close":"99"}]*60
        x=evaluate(a,"BTCUSDT");y=evaluate(b,"BTCUSDT")
        self.assertEqual(x["ranking"],y["ranking"])
        self.assertEqual(x["candidate"],y["candidate"])
        self.assertFalse(x["paper_orders"])
        self.assertEqual(x["initial_capital"],"1000")
    def test_long_short(self):
        bars=[(D(100),D(101))]*80
        self.assertGreater(simulate(bars,"long",5,60,80)["net"],0)
        self.assertLess(simulate(bars,"short",5,60,80)["net"],0)
        self.assertEqual(simulate(bars,"cash",5,60,80)["net"],0)
    def test_gap(self):
        bars=[(D(100),D(100))]*80
        bars[60]=(D(100),D(40))
        a=simulate(bars,"long",5,60,61)
        self.assertEqual(a["liquidations"],1)
        self.assertGreater(a["net"],-.11)
