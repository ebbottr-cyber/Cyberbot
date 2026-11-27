import os,unittest,subprocess,sys,time
from contextlib import nullcontext
from unittest.mock import patch
from cyberbot import futures_watchdog as w

SYM="BTCUSDT"
def event(stage="training_collect",status="captured"):
    return {"version":w.supervisor.VERSION,"symbol":SYM,"stage":stage,"status":status,"real_orders":False}

class WatchdogTests(unittest.TestCase):
    def test_heartbeat_and_network_failure_streak(self):
        h=w.Health(SYM,0)
        self.assertIsNone(h.timeout(149));self.assertEqual(h.timeout(150),"heartbeat_timeout")
        self.assertIsNone(h.accept(event(status="rejected"),150))
        self.assertIsNone(h.accept(event(),151))
        for i in range(2):self.assertIsNone(h.accept(event(status="missed_slot"),152+i))
        self.assertEqual(h.accept(event(status="rejected"),154),"training_collect_unhealthy")
        self.assertEqual(h.accept({**event(),"real_orders":True},155),"invalid_child_event")
    def test_recovery_child_cannot_rearm_auto(self):
        env={"CYBERBOT_FUTURES_AUTO_PAPER_ENABLED":"1","CYBERBOT_FUTURES_AUTO_PAPER_CONFIRMED":"1"}
        args,initial=w.child_spec(SYM,20,True,True,False,env=env)
        self.assertIn("--automatic",args)
        args,after=w.child_spec(SYM,20,True,True,True,env=env)
        self.assertNotIn("--automatic",args);self.assertIn("--paper",args)
        self.assertEqual(after["CYBERBOT_PILOT_KILL_SWITCH"],"1")
        self.assertEqual(after["CYBERBOT_FUTURES_AUTO_PAPER_CONFIRMED"],"0")
        self.assertEqual(env["CYBERBOT_FUTURES_AUTO_PAPER_CONFIRMED"],"1")
    def test_bounded_backoff_and_recovery_mode(self):
        now=[0];seen=[];events=[]
        def runner(sym,minutes,paper,automatic,recovered,deadline,emit):
            seen.append((paper,automatic,recovered));return "heartbeat_timeout"
        def sleep(n):now[0]+=n
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_WATCHDOG_ENABLED":"1"}),patch.object(w.supervisor,"validate"),patch.object(w.supervisor,"lease",return_value=nullcontext()):
            d=w.run(SYM,20,paper=True,automatic=True,monotonic=lambda:now[0],sleep=sleep,runner=runner,emit=events.append)
        self.assertEqual(d["status"],"restart_limit_reached")
        self.assertEqual(now[0],105);self.assertEqual(d["restarts"],3)
        self.assertEqual(seen,[(True,True,False)]+[(True,True,True)]*3)
        self.assertFalse(d["automatic_rearmed"])
    def test_clean_exit_and_stop_error_never_restart(self):
        for reason in ("completed","interrupted","session_deadline","child_start_or_stop_error"):
            with patch.dict(os.environ,{"CYBERBOT_FUTURES_WATCHDOG_ENABLED":"1"}),patch.object(w.supervisor,"validate"),patch.object(w.supervisor,"lease",return_value=nullcontext()):
                d=w.run(SYM,20,runner=lambda *a:reason,emit=lambda _:None)
                self.assertEqual(d["restarts"],0)
    def test_disabled_before_process(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_WATCHDOG_ENABLED":"0"}),patch.object(w.supervisor,"lease",side_effect=AssertionError("disabled")):
            with self.assertRaises(ValueError):w.run(SYM,1)
    def test_real_child_completion_protocol(self):
        # Only an offline fixture child, not the actual provider.
        import json
        e={**event(),"status":"session_ended"}
        cmd=[sys.executable,"-u","-c","print("+repr(json.dumps(e))+")"]
        with patch.object(w,"child_spec",return_value=(cmd,dict(os.environ))):
            d=w.monitor(SYM,1,False,False,False,time.monotonic()+15,lambda _:None)
        self.assertEqual(d,"completed")
