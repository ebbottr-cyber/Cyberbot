import tempfile
import unittest
from pathlib import Path
from cyberbot.strategy_memory import initial,update,filter_choice,StrategyMemory
from cyberbot.adaptive import evaluate
from cyberbot.regimes import demo_rows

def block(i,ret=-1,dd=2):
    return {"strategy":"trend","start_key":f"{i:06d}","end_key":f"{i+19:06d}","return_pct":ret,"double_cost_return_pct":ret,"drawdown_pct":dd,"double_cost_drawdown_pct":dd,"closed_trades":1}

class MemoryTests(unittest.TestCase):
    def test_quarantine_recovery(self):
        s=update(initial(),block(0))
        self.assertEqual(s["status"],"observing")
        s=update(s,block(20))
        self.assertEqual(s["status"],"quarantined")
        for i in (40,60,80):s=update(s,block(i,ret=1))
        self.assertEqual(s["status"],"observing")
        self.assertEqual(update(s,block(100,ret=1,dd=11))["status"],"quarantined")
    def test_persistence_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"learn.sqlite3";j=StrategyMemory(p)
            result={"mode":"synthetic","market":"BIST","symbol":"demo","evidence_blocks":[block(0),block(20)]}
            a=j.record(result);self.assertEqual(a["accepted"],2)
            self.assertEqual(a["states"]["trend"]["status"],"quarantined")
            self.assertEqual(StrategyMemory(p).record(result)["accepted"],0)
            result["evidence_blocks"]=[block(30,1),block(40,1),block(60,1)]
            a=j.record(result);self.assertEqual(a["accepted"],2)
            self.assertEqual(a["states"]["trend"]["status"],"quarantined")
            result["evidence_blocks"]=[block(80,1)]
            self.assertEqual(j.record(result)["states"]["trend"]["status"],"observing")
            self.assertEqual(j.read("historical_unverified","BIST","demo")["states"]["trend"]["blocks"],0)
    def test_filter(self):
        d={"strategy":"trend","ranking":[{"strategy":"trend","eligible":True}]}
        self.assertEqual(filter_choice(d,{"trend":{"status":"quarantined"}})["strategy"],"cash")
    def test_replay_blocks(self):
        d=evaluate(demo_rows("BIST"),mode="synthetic",market="BIST",symbol="demo")
        self.assertEqual(len(d["evidence_blocks"]),d["completed_blocks"]*3)
        self.assertFalse(d["paper_orders"])
