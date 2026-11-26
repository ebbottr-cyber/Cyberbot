import os,tempfile,unittest,subprocess,sys,sqlite3
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from cyberbot.pilot_supervisor import supervise,single_instance,PilotError
from cyberbot import observed_pilot as p

class PilotSupervisorTests(unittest.TestCase):
    def test_restart_budget_and_process_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            env={"CYBERBOT_DB":str(root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(root/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(root/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_PILOT_LOOP_ENABLED":"1","CYBERBOT_PILOT_LOOP_MARKETS":"BIST","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_PILOT_SHADOW_ENABLED":"1","CYBERBOT_PILOT_INGRESS_ENABLED":"1","CYBERBOT_PILOT_SUPERVISOR_ENABLED":"1"}
            with patch.dict(os.environ,env):
                with patch.dict(os.environ,{"CYBERBOT_PILOT_SUPERVISOR_ENABLED":"0"}):
                    with self.assertRaises(PilotError):supervise(cycles=1,runner=lambda:"ok")
                self.assertEqual(list(root.iterdir()),[])
                delays=[];results=iter(["timeout","child_failed","ok","timeout","timeout","timeout"])
                self.assertEqual(supervise(cycles=6,runner=lambda:next(results),sleep=delays.append),1)
                self.assertEqual(delays,[60,60,20,60,60])
                code="""from cyberbot.pilot_supervisor import single_instance
import sys
with single_instance():
    print('locked',flush=True)
    sys.stdin.read()
"""
                proc=subprocess.Popen([sys.executable,"-c",code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    self.assertEqual(proc.stdout.readline().strip(),"locked")
                    with self.assertRaises(PilotError):
                        with single_instance():pass
                finally:
                    proc.kill();proc.communicate(timeout=10)
                with single_instance():pass
                self.assertFalse((root/"pilot.sqlite3").exists())
    def test_interrupted_sqlite_transaction_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/"journal.sqlite3"
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TABLE journal(value TEXT)");db.execute("INSERT INTO journal VALUES('committed')");db.commit()
            code="import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute('BEGIN IMMEDIATE'); db.execute(\"INSERT INTO journal VALUES('interrupted')\"); print('ready',flush=True); sys.stdin.read()"
            proc=subprocess.Popen([sys.executable,"-c",code,str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:self.assertEqual(proc.stdout.readline().strip(),"ready")
            finally:proc.kill();proc.communicate(timeout=10)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("PRAGMA quick_check").fetchone(),("ok",))
                self.assertEqual(db.execute("SELECT value FROM journal").fetchall(),[("committed",)])
