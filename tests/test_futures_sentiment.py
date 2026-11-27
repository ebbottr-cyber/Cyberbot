"""Offline Futures sentiment regression tests."""
import os,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import httpx
from cyberbot.providers.futures_sentiment import (GLOBAL,TAKER,TOP_ACCOUNT,TOP_POSITION,
    run,summarize,fetch,PilotError)

NOW=datetime(2026,1,1,12,2,tzinfo=timezone.utc)
END=NOW-timedelta(minutes=2)
def ms(t):return int(t.timestamp()*1000)
def fixture():
    ratio={"symbol":"BTCUSDT","timestamp":ms(END),"longAccount":".6","shortAccount":".4","longShortRatio":"1.5"}
    return {GLOBAL:[dict(ratio)],TOP_ACCOUNT:[dict(ratio)],TOP_POSITION:[dict(ratio)],
            TAKER:[{"timestamp":ms(END-timedelta(minutes=5)),"buyVol":"60","sellVol":"40","buySellRatio":"1.5"}]}

class FuturesSentimentTests(unittest.TestCase):
    def test_common_closed_period_and_optional_top(self):
        raw=fixture()
        raw[TAKER].append({**raw[TAKER][0],"timestamp":ms(END)})
        d=summarize(raw,"BTCUSDT",NOW)
        self.assertEqual(d["period_end"],END.isoformat())
        self.assertEqual(d["taker_volume"]["volume_imbalance"],"0.2")
        self.assertIsNone(d["top_trader_positions"])
        self.assertIsNone(d["directional_signal"])
        self.assertFalse(d["real_orders"])
        full=summarize(raw,"BTCUSDT",NOW,include_top=True)
        self.assertEqual(full["top_trader_positions"]["long_share"],"0.6")
        self.assertFalse(full["pilot_applied"])

    def test_reject_inconsistent_wrong_and_unaligned_evidence(self):
        for endpoint,changes in ((GLOBAL,{"symbol":"ETHUSDT"}),
                (GLOBAL,{"longShortRatio":"0.2"}),(GLOBAL,{"shortAccount":"0"}),
                (GLOBAL,{"timestamp":ms(NOW+timedelta(seconds=1))}),
                (TAKER,{"sellVol":"0"}),(TAKER,{"buyVol":"NaN"}),
                (TAKER,{"timestamp":ms(END-timedelta(minutes=6))}),
                (TAKER,{"timestamp":ms(END-timedelta(minutes=30))})):
            with self.subTest(endpoint=endpoint,changes=changes):
                raw=fixture();raw[endpoint][0].update(changes)
                with self.assertRaises(PilotError):summarize(raw,"BTCUSDT",NOW)

    def test_run_is_explicit_and_bounded(self):
        env={"CYBERBOT_BINANCE_OBSERVED_ENABLED":"1","CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1",
             "CYBERBOT_FUTURES_PILOT_SYMBOL":"BTCUSDT","CYBERBOT_BINANCE_SENTIMENT_DATA_KEY":""}
        calls=[]
        def transport(e,p):
            calls.append(e);self.assertEqual(p,{"symbol":"BTCUSDT","period":"5m","limit":3})
            return fixture()[e]
        with patch.dict(os.environ,env):
            self.assertTrue(run(transport=transport,clock=lambda:NOW)["transport_mocked"])
            self.assertEqual(calls,[GLOBAL,TAKER])
            calls.clear()
            with self.assertRaises(PilotError):run(include_top=True,transport=transport,clock=lambda:NOW)
            self.assertEqual(calls,[])
            with patch.dict(os.environ,{"CYBERBOT_BINANCE_SENTIMENT_DATA_KEY":"fixture-only"}):
                run(include_top=True,transport=transport,clock=lambda:NOW)
                self.assertEqual(calls,[GLOBAL,TAKER,TOP_ACCOUNT,TOP_POSITION])
            calls.clear()
            with patch.dict(os.environ,{"CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"0"}):
                with self.assertRaises(PilotError):run(transport=transport,clock=lambda:NOW)
                self.assertEqual(calls,[])

    def test_key_only_sent_to_top_data_endpoints(self):
        seen=[]
        def handler(req):
            seen.append(req)
            return httpx.Response(200,json=[])
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            for endpoint in (GLOBAL,TAKER,TOP_ACCOUNT,TOP_POSITION):
                fetch(client,endpoint,"BTCUSDT","fixture-only")
            with self.assertRaises(PilotError):fetch(client,"/fapi/v1/order","BTCUSDT","fixture-only")
        self.assertEqual(len(seen),4)
        for req in seen:
            self.assertEqual(req.method,"GET")
            self.assertEqual(req.url.host,"fapi.binance.com")
            self.assertEqual(req.headers.get("X-MBX-APIKEY"),
                             "fixture-only" if req.url.path in (TOP_ACCOUNT,TOP_POSITION) else None)
