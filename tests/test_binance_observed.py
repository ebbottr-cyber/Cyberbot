import os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot.providers.binance_observed import run,BOOK,MARK,INFO,FUNDING,SOURCE,PilotError,PERIOD_MS,OPEN_INTEREST,market_context,DEPTH,orderbook_context
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
                if endpoint==DEPTH:
                    self.assertEqual(params,{"symbol":"BTCUSDT","limit":20})
                    return {"lastUpdateId":1,"T":ms,"E":ms,"bids":[["100","10"]],"asks":[["100.1","10"]]}
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
                depth=run(depth_probe=True,transport=mock,clock=lambda:t)["orderbook_context"]
                self.assertEqual(calls,[INFO,BOOK,MARK,DEPTH])
                self.assertTrue(depth["ticker_top_matches"])
                self.assertFalse(depth["execution_verified"])
                self.assertEqual(list(p.iterdir()),[])
                calls.clear()
                with self.assertRaises(PilotError):run(apply=True,depth_probe=True,transport=mock,clock=lambda:t)
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

    def test_orderbook_depth_and_sweep(self):
        from decimal import Decimal as D
        t=datetime(2026,1,1,tzinfo=timezone.utc);ms=int(t.timestamp()*1000)
        book={"symbol":"BTCUSDT","time":ms,"bidPrice":"99","askPrice":"101","bidQty":"1","askQty":"1"}
        raw={"lastUpdateId":1,"T":ms,"E":ms,
             "bids":[[str(99-i),"1"] for i in range(5)],
             "asks":[[str(101+i),"1"] for i in range(5)]}
        d=orderbook_context(raw,book,"BTCUSDT",t)
        self.assertTrue(d["ticker_top_matches"])
        self.assertEqual(len(d["depth_bands"]),1)
        self.assertEqual(d["depth_bands"][0]["bid_notional_usdt"],"485")
        self.assertEqual(d["depth_bands"][0]["ask_notional_usdt"],"515")
        self.assertEqual(D(d["depth_bands"][0]["notional_imbalance"]),D("-.03"))
        self.assertEqual(D(d["indicative_sweeps"][0]["buy_vwap"]),D(101))
        self.assertEqual(D(d["indicative_sweeps"][1]["buy_vwap"]),D(103))
        self.assertIsNone(d["indicative_sweeps"][2]["buy_vwap"])
        self.assertIsNone(d["indicative_sweeps"][2]["sell_vwap"])
        self.assertIsNone(d["directional_signal"])
        self.assertFalse(d["real_orders"])
        self.assertFalse(d["full_book_verified"])

    def test_orderbook_rejects_invalid_snapshots(self):
        t=datetime(2026,1,1,tzinfo=timezone.utc);ms=int(t.timestamp()*1000)
        book={"symbol":"BTCUSDT","time":ms,"bidPrice":"99","askPrice":"101","bidQty":"1","askQty":"1"}
        raw={"lastUpdateId":1,"T":ms,"E":ms,"bids":[["99","1"]],"asks":[["101","1"]]}
        for change in ({"T":ms-4000},{"E":ms+1},{"lastUpdateId":True},{"symbol":"ETHUSDT"},
                       {"bids":[["99","1"],["99","2"]]},{"asks":[["98","1"]]},
                       {"asks":[["101","0"]]},{"bids":[]},{"bids":[["99","NaN"]]},
                       {"bids":[[str(99-i),"1"] for i in range(21)]}):
            with self.subTest(change=change),self.assertRaises(PilotError):
                orderbook_context({**raw,**change},book,"BTCUSDT",t)
        d=orderbook_context(raw,{**book,"bidQty":"2"},"BTCUSDT",t)
        self.assertFalse(d["ticker_top_matches"])
