import json,os,unittest
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot.providers.futures_liquidations import parse_event,run,HOST,PilotError

START=datetime(2026,1,1,12,0,tzinfo=timezone.utc)
ENV={"CYBERBOT_BINANCE_OBSERVED_ENABLED":"1","CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1",
     "CYBERBOT_FUTURES_LIQUIDATION_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":"BTCUSDT"}
def event(offset=1,side="SELL"):
    ms=int((START+timedelta(seconds=offset)).timestamp()*1000)
    return {"e":"forceOrder","E":ms,"o":{"s":"BTCUSDT","S":side,"q":"2","ap":"100",
            "X":"FILLED","l":"1","z":"2","T":ms}}
class LiquidationTests(unittest.TestCase):
    def test_direction_and_notional(self):
        for side,expected in (("SELL","LONG"),("BUY","SHORT")):
            d=parse_event(event(side=side),"BTCUSDT",START+timedelta(seconds=1))
            self.assertEqual(d["liquidated_side"],expected)
            self.assertEqual(d["reported_cumulative_notional_usdt"],"200")
    def test_bad_data(self):
        for update in ({"z":"3"},{"ap":"0"},{"S":"OTHER"},{"s":"ETHUSDT"},{"l":"3"},{"z":"NaN"}):
            raw=event();raw["o"].update(update)
            with self.subTest(update=update),self.assertRaises(PilotError):
                parse_event(raw,"BTCUSDT",START+timedelta(seconds=1))
        with self.assertRaises(PilotError):parse_event(event(),"BTCUSDT",START)
    def collect(self,items,disconnect=False):
        elapsed=[0];calls=[]
        class Socket:
            def recv(self,timeout):
                if items:
                    item=items.pop(0);elapsed[0]+=1
                    return json.dumps(item)
                if disconnect:raise OSError("offline")
                elapsed[0]+=timeout;raise TimeoutError
        @contextmanager
        def connector(url):
            calls.append(url);yield Socket()
        with patch.dict(os.environ,ENV):
            result=run(connector=connector,clock=lambda:START+timedelta(seconds=elapsed[0]),
                       monotonic=lambda:elapsed[0])
        self.assertEqual(calls,[HOST+"btcusdt@forceOrder"])
        return result
    def test_cluster_dedup_and_incomplete_market_coverage(self):
        d=self.collect([event(1),event(1),event(2),event(3),event(4,"BUY")])
        self.assertTrue(d["window_complete"])
        self.assertEqual(d["deduplicated_messages"],1)
        self.assertEqual(d["filled_snapshot_counts"],{"LONG":3,"SHORT":1})
        self.assertEqual(d["clusters"][0]["filled_snapshots"],3)
        for key in ("market_coverage_complete","totals_are_unique_trade_volume",
                    "cascade_prediction_verified","pilot_applied","real_orders"):
            self.assertIs(d[key],False)
    def test_disconnect_and_silent_window(self):
        d=self.collect([event()],disconnect=True)
        self.assertFalse(d["window_complete"])
        self.assertEqual(d["stop_reason"],"OSError")
        self.assertEqual(d["filled_snapshot_counts"]["LONG"],1)
        d=self.collect([])
        self.assertTrue(d["window_complete"])
        self.assertFalse(d["market_coverage_complete"])
    def test_disabled_no_connection(self):
        with patch.dict(os.environ,{**ENV,"CYBERBOT_FUTURES_LIQUIDATION_ENABLED":"0"}):
            with self.assertRaises(PilotError):run(connector=lambda _:self.fail("connected"))
