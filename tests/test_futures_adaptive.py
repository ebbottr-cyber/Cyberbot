import unittest
import tempfile
from pathlib import Path
from decimal import Decimal as D
from cyberbot.futures_adaptive import evaluate
from cyberbot.futures_research import rows_for
from cyberbot.strategy_memory import StrategyMemory,initial,update,filter_choice

def bars(symbol):
    return [tuple(D(r[k]) for k in ("open","close")) for r in rows_for(symbol)]

class FuturesAdaptiveTests(unittest.TestCase):
    def test_causal_and_cash_default(self):
        data=bars("BTCUSDT")
        a=evaluate(data)
        b=evaluate(data[:-20]+[(D(100),D(40))]*20)
        self.assertEqual(a["decisions"][:-1],b["decisions"][:-1])
        for key in ("selected","window","regime","ranking"):
            self.assertEqual(a["decisions"][-1][key],b["decisions"][-1][key])
        self.assertEqual(a["decisions"][0]["selected"],"cash")
        self.assertFalse(a["paper_orders"])
        self.assertEqual(a["initial_capital"],"1000")
    def test_liquidation_quarantine(self):
        block={"end_key":"000019","return_pct":1,"double_cost_return_pct":1,"drawdown_pct":1,"double_cost_drawdown_pct":1,"closed_trades":5,"liquidations":1}
        s=update(initial(),block)
        self.assertEqual(s["reason"],"liquidation")
        self.assertEqual(s["status"],"quarantined")
        self.assertEqual(filter_choice({"ranking":[{"strategy":"trend","eligible":True}]},{"trend":s})["strategy"],"cash")
        for i in range(3):
            s=update(s,{**block,"liquidations":0,"end_key":f"{39+i*20:06d}"})
        self.assertEqual(s["status"],"observing")
    def test_memory_scoped_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            j=StrategyMemory(Path(tmp)/"learn.sqlite3")
            a={**evaluate(bars("BTCUSDT")),"market":"FUTURES","symbol":"BTCUSDT"}
            first=j.record(a)
            self.assertGreater(first["accepted"],0)
            self.assertEqual(j.record(a)["accepted"],0)
            self.assertEqual(j.read("synthetic","FUTURES","ETHUSDT")["states"]["trend"]["blocks"],0)
