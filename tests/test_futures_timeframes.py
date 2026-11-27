"""Offline tests for bounded closed-candle multi-timeframe research."""
import os,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import httpx
from cyberbot.providers.futures_timeframes import FRAMES,LIMIT,KLINES,parse,summarize,run,fetch,PilotError

NOW=datetime(2026,1,1,12,2,tzinfo=timezone.utc)
CUTOFF=int(NOW.timestamp()*1000)-3000
ENV={"CYBERBOT_BINANCE_OBSERVED_ENABLED":"1","CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1",
     "CYBERBOT_FUTURES_TIMEFRAMES_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":"BTCUSDT"}
def rows(frame,cutoff=CUTOFF,direction=1):
    step=FRAMES[frame];end=cutoff//step*step
    data=[]
    for i in range(LIMIT):
        start=end-(LIMIT-i)*step
        price=100+direction*i
        data.append([start,str(price),str(price+1),str(price-1),str(price),"100",
                     start+step-1,"10000",10,"50","5000","0"])
    return data
class TimeframeTests(unittest.TestCase):
    def test_alignment_and_conflict(self):
        for direction,expected in ((1,"aligned_up"),(-1,"aligned_down"),(0,"mixed_or_neutral")):
            d=summarize({f:rows(f,direction=direction) for f in FRAMES},"BTCUSDT",CUTOFF)
            self.assertEqual(d["alignment"],expected)
            self.assertEqual(d["higher_timeframes_agree"],direction!=0)
            self.assertIsNone(d["directional_signal"])
            self.assertFalse(d["pilot_applied"])
            self.assertFalse(d["real_orders"])
        mixed={f:rows(f) for f in FRAMES};mixed["4h"]=rows("4h",direction=-1)
        self.assertEqual(summarize(mixed,"BTCUSDT",CUTOFF)["alignment"],"mixed_or_neutral")
        self.assertFalse(summarize(mixed,"BTCUSDT",CUTOFF)["higher_timeframes_agree"])

    def test_invalid_candles(self):
        for index,value in ((0,0),(6,CUTOFF+1),(2,"1"),(4,"NaN"),(9,"101"),(8,True),(5,"-1")):
            raw=rows("1m");raw[-1][index]=value
            with self.subTest(index=index),self.assertRaises(PilotError):parse(raw,"1m",CUTOFF)
        raw=rows("1m");raw[-2]=raw[-1][:]
        with self.assertRaises(PilotError):parse(raw,"1m",CUTOFF)
        with self.assertRaises(PilotError):parse(rows("1m")[:-1],"1m",CUTOFF)

    def test_fixed_cutoff_and_bounded_requests(self):
        calls=[]
        def transport(endpoint,p):
            calls.append(p);self.assertEqual(endpoint,KLINES)
            return rows(p["interval"])
        with patch.dict(os.environ,ENV):
            d=run(transport=transport,clock=lambda:NOW)
            self.assertTrue(d["transport_mocked"])
            self.assertEqual([p["interval"] for p in calls],list(FRAMES))
            for p in calls:
                self.assertEqual(p["limit"],21)
                step=FRAMES[p["interval"]]
                self.assertEqual(p["endTime"],CUTOFF//step*step-1)
            calls.clear()
            with patch.dict(os.environ,{"CYBERBOT_FUTURES_TIMEFRAMES_ENABLED":"0"}):
                with self.assertRaises(PilotError):run(transport=transport,clock=lambda:NOW)
            self.assertEqual(calls,[])

    def test_elapsed_limit(self):
        ticks=iter([NOW,NOW+timedelta(seconds=31)])
        with patch.dict(os.environ,ENV):
            with self.assertRaises(PilotError):
                run(transport=lambda *args:self.fail("late request"),clock=lambda:next(ticks))

    def test_fixed_public_route(self):
        seen=[]
        def handler(request):
            seen.append(request);return httpx.Response(200,json=rows("1m"))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            self.assertEqual(len(fetch(client,"BTCUSDT","1m",CUTOFF)),LIMIT)
            with self.assertRaises(PilotError):fetch(client,"BTCUSDT","1d",CUTOFF)
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0].url.host,"fapi.binance.com")
        self.assertEqual(seen[0].url.path,KLINES)
        self.assertEqual(seen[0].method,"GET")
        self.assertNotIn("X-MBX-APIKEY",seen[0].headers)
