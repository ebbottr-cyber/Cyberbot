import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cyberbot.readiness import snapshot
from cyberbot.capital import Portfolio
class ReadinessTests(unittest.TestCase):
    def test_read_only_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            env={"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_EQUITY_RESEARCH_RIGHTS_CONFIRMED":"0","CYBERBOT_SOLANA_READ_ENABLED":"0"}
            with patch.dict(os.environ,env):
                d=snapshot()
                self.assertEqual(len(d["markets"]),5)
                self.assertFalse(d["live_paper_enabled"])
                self.assertFalse(d["real_orders"])
                self.assertEqual(list(p.iterdir()),[])
                Portfolio()
                before={x:x.read_bytes() for x in p.rglob("*.sqlite3")}
                d=snapshot()
                self.assertTrue(all(x["database"]=="ok" for x in d["markets"]))
                self.assertTrue(all(x["status"]=="blocked" for x in d["markets"]))
                self.assertEqual({x:x.read_bytes() for x in before},before)
                with patch.dict(os.environ,{"CYBERBOT_EBBOT_DB":env["CYBERBOT_DB"]}):
                    self.assertEqual(snapshot()["database_isolation"],"failed")
    def test_permission_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            env={"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":str(p/"archive.sqlite3"),"CYBERBOT_EQUITY_RESEARCH_RIGHTS_CONFIRMED":"0"}
            with patch.dict(os.environ,env),patch("cyberbot.readiness.history",side_effect=AssertionError("permission missing")):
                d=snapshot()
                self.assertEqual(d["markets"][0]["data"]["status"],"rights_not_confirmed")
