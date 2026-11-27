import os,unittest
from datetime import datetime,timezone,timedelta
from contextlib import nullcontext
from unittest.mock import patch
from cyberbot import futures_supervisor as s
AT=datetime(2026,1,1,12,tzinfo=timezone.utc)
class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.t=AT;self.events=[]
    def clock(self):return self.t
    def sleep(self,n):self.t+=timedelta(seconds=n)
    def collect(self,symbol,*,clock):
        self.assertEqual(clock().second,40)
        return {"row":{"at":(clock().replace(second=0)+timedelta(minutes=1)).isoformat()}}
    def save(self,record,*,clock):
        self.assertEqual(clock().isoformat(),record["row"]["at"])
        return {"status":"recorded"}
    def test_research_only_slots_and_final_save(self):
        with patch.object(s,"validate"),patch.object(s,"lease",return_value=nullcontext()),patch.object(s.training,"collect",side_effect=self.collect),patch.object(s.training,"save",side_effect=self.save),patch.object(s.forward,"tick",return_value={"status":"waiting_for_data"}) as tick,patch.object(s.binance,"run",side_effect=AssertionError("paper not permitted")):
            d=s.supervise("BTCUSDT",3,clock=self.clock,sleep=self.sleep,emit=self.events.append)
            self.assertEqual(d["counts"]["recorded"],3);self.assertEqual(tick.call_count,2)
            self.assertFalse(d["real_orders"])
    def test_missed_slots_no_catchup(self):
        def slow_collect(symbol,*,clock):
            r=self.collect(symbol,clock=clock);self.t+=timedelta(seconds=30);return r
        with patch.object(s,"validate"),patch.object(s,"lease",return_value=nullcontext()),patch.object(s.training,"collect",side_effect=slow_collect),patch.object(s.training,"save",side_effect=AssertionError("late save")):
            d=s.supervise("BTCUSDT",2,clock=self.clock,sleep=self.sleep,emit=self.events.append)
            self.assertEqual(d["counts"]["recorded"],0);self.assertEqual(d["counts"]["missed"],2)
    def test_no_automatic_entry_without_contiguous_observations(self):
        def observe(**kw):
            return {"applied":True,"real_orders":False,"ingress":{"status":"observation"},"source_at":self.clock().isoformat()}
        with patch.object(s,"validate"),patch.object(s,"lease",return_value=nullcontext()),patch.object(s.training,"collect",side_effect=self.collect),patch.object(s.training,"save",side_effect=self.save),patch.object(s.forward,"tick",return_value={"status":"waiting_for_data"}),patch.object(s.binance,"run",side_effect=observe) as calls,patch.object(s.auto,"run",side_effect=AssertionError("no fresh prediction")):
            d=s.supervise("BTCUSDT",2,paper=True,automatic=True,clock=self.clock,sleep=self.sleep,emit=self.events.append)
            self.assertGreater(d["counts"]["paper_observations"],0)
            self.assertTrue(all(not c.kwargs["auto_paper"] for c in calls.call_args_list))
    def test_disabled_before_lease(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_SUPERVISOR_ENABLED":"0"}),patch.object(s,"lease",side_effect=AssertionError("disabled")):
            with self.assertRaises(ValueError):s.supervise("BTCUSDT",1)
