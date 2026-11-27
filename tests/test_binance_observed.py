import os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot.providers.binance_observed import run,BOOK,MARK,INFO,FUNDING,SOURCE,PilotError,PERIOD_MS,OPEN_INTEREST,market_context
from cyberbot import futures_pilot as fut
class BinanceObservedTests(unittest.TestCase):
    def test_probe_apply_funding(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);t=datetime(2026,1,1,7,59,55,tzinfo=timezone.utc);calls=[];bad=False;fund=[]
            env={"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(p/"learn.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(p/"pilot.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":"","CYBERBOT_BINANCE_OBSERVED_ENABLED":"1","CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1","CYBERBOT_OBSERVED_PILOT_ENABLED":"1","CYBERBOT_OBSERVED_PRICE_RIGHTS_CONFIRMED":"1","CYBERBOT_FUTURES_PILOT_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":"BTCUSDT","CYBERBOT_PILOT_INGRESS_ENABLED":"1","CYBERBOT_INGRESS_SOURCE_FUTURES":SOURCE}
            def mock(endpoint,params):
                calls.append(endpoint);ms=int(t.timestamp()*1000)
                if endpoint==INFO:return [{"symbol":"BTCUSDT","fundingIntervalHours":4}] if bad else []
                if endpoint==BOOK:return {"symbol":"BTCUSDT","time":ms,"bidPrice":"100","askPrice":"100.1","bidQty":"10","askQty":"10"}
                if endpoint==MARK:return {"symbol":"BTCUSDT","time":ms,"markPrice":"100","indexPrice":"100","lastFundingRate":".0001","nextFundingTime":(ms//PERIOD_MS+1)*PERIOD_MS}
                if endpoint==OPEN_INTEREST:return {"symbol":"BTCUSDT","time":ms,"openInterest":"500"}
                if endpoint==FUNDING:return fund
                raise AssertionError(endpoint)
            def poll(apply=False):return run(apply=apply,transport=mock,clock=lambda:t)
            with patch.dict(os.environ,env):
                with patch.dict(os.environ,{"CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"0"}):
                    with self.assertRaises(PilotError):poll()
                    self.assertEqual(calls,[])
                self.assertFalse(poll()["applied"]);self.assertEqual(list(p.iterdir()),[])
                calls.clear()
                context=run(context_probe=True,transport=mock,clock=lambda:t)["market_context"]
                self.assertEqual(calls,[INFO,BOOK,MARK,OPEN_INTEREST])
                self.assertEqual(context["indicative_open_interest_usdt"],"50000")
                self.assertIsNone(context["directional_signal"])
                self.assertFalse(context["real_orders"])
                self.assertEqual(list(p.iterdir()),[])
                calls.clear()
                with self.assertRaises(PilotError):run(apply=True,context_probe=True,transport=mock,clock=lambda:t)
                self.assertEqual(calls,[])
                bad=True
                with self.assertRaises(PilotError):poll()
                bad=False;self.assertTrue(poll(True)["applied"])
                fut.request("LONG",clock=lambda:t);t+=timedelta(seconds=1);poll(True)
                self.assertIsNotNone(fut.snapshot(clock=lambda:t)["position"])
                t+=timedelta(seconds=4)
                with self.assertRaises(PilotError):poll(True)
                self.assertTrue(fut.snapshot(clock=lambda:t)["funding_due"])
                fund.append({"symbol":"BTCUSDT","fundingTime":int(t.timestamp()*1000),"fundingRate":".0001","markPrice":"100"})
                poll(True);self.assertEqual(fut.snapshot(clock=lambda:t)["funding_events"],1)
                self.assertEqual(list(p.iterdir()),[p/"pilot.sqlite3"])
                self.assertIn(FUNDING,calls)

    def test_context_rejects_stale_wrong_symbol_and_handles_empty_book(self):
        t=datetime(2026,1,1,tzinfo=timezone.utc);ms=int(t.timestamp()*1000);sym="BTCUSDT"
        book={"symbol":sym,"time":ms,"bidPrice":"100","askPrice":"101","bidQty":"3","askQty":"1"}
        mark={"symbol":sym,"time":ms,"markPrice":"100","indexPrice":"100","lastFundingRate":"-.0001"}
        oi={"symbol":sym,"time":ms,"openInterest":"10"}
        d=market_context(book,mark,oi,sym,t)
        self.assertEqual(d["best_level_qty_imbalance"],"0.5")
        self.assertFalse(d["settled_funding_verified"])
        for change in ({"time":ms-4000},{"time":ms+1},{"symbol":"ETHUSDT"},{"openInterest":"NaN"}):
            with self.assertRaises(PilotError):market_context(book,mark,{**oi,**change},sym,t)
        empty=market_context({**book,"bidQty":"0","askQty":"0"},mark,oi,sym,t)
        self.assertIsNone(empty["best_level_qty_imbalance"])
