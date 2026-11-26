import os,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cyberbot.development import overview
from cyberbot.research_pipeline import PipelineJournal
from cyberbot.strategy_memory import StrategyMemory

class DevelopmentTests(unittest.TestCase):
    def test_empty_and_read_only_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);db=p/"learn.sqlite3"
            with patch.dict(os.environ,{"CYBERBOT_LEARNING_DB":str(db),"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":""}):
                self.assertEqual(len(overview("synthetic")["markets"]),5)
                self.assertFalse(db.exists())
                j=PipelineJournal(db)
                for key,mode,market,symbol in [("a","synthetic","FUTURES","BTCUSDT"),("b","synthetic","FUTURES","ETHUSDT"),("c","historical_unverified","BIST","THYAO.IS")]:
                    j.save({"id":key,"mode":mode,"market":market,"symbol":symbol,"summary":{"next_candidate":"trend"},"ranking":[]})
                memory=StrategyMemory(db)
                memory.record({"mode":"synthetic","market":"FUTURES","symbol":"BTCUSDT","evidence_blocks":[{"strategy":"trend","start_key":"000060","end_key":"000079","return_pct":-5,"double_cost_return_pct":-6,"drawdown_pct":6,"double_cost_drawdown_pct":7,"closed_trades":1,"liquidations":1}]})
                before=db.read_bytes()
                d=overview("synthetic")
                self.assertEqual(d["total_experiments"],2)
                m=next(x for x in d["markets"] if x["market"]=="FUTURES")
                self.assertEqual(m["experiments"],2)
                a=next(x for x in m["latest"] if x["symbol"]=="BTCUSDT")
                self.assertEqual(a["candidate_after_quarantine"],"cash")
                self.assertEqual(a["memory"]["trend"]["status"],"quarantined")
                self.assertEqual(overview("historical_unverified")["total_experiments"],1)
                self.assertEqual(db.read_bytes(),before)
                self.assertFalse((p/"paper.sqlite3").exists())
