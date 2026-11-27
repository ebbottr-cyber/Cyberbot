"""Offline indicator math and isolated observation tests."""
import os,unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from unittest.mock import patch
from cyberbot.providers import futures_momentum as m,futures_timeframes as tf
from cyberbot.providers.binance_observed import BOOK
from cyberbot.observed_pilot import PilotError

NOW=datetime(2026,1,1,12,2,tzinfo=timezone.utc)
ENV={"CYBERBOT_BINANCE_OBSERVED_ENABLED":"1","CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1",
     "CYBERBOT_FUTURES_MOMENTUM_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":"BTCUSDT"}
def series(direction):
    return [(p,p+1,p-1,p,D(100)) for p in (D(100+i*direction) for i in range(60))]
class MomentumTests(unittest.TestCase):
    def test_flat_indicators(self):
        d=m.indicators(series(0))
        for key,val in {"rsi14":50,"macd_12_26":0,"macd_histogram":0,"atr14":2,
                        "upside_semivariance_20":0,"downside_semivariance_20":0}.items():
            self.assertEqual(D(d[key]),D(val))
    def test_direction_and_macd(self):
        for direction in (1,-1):
            d=m.indicators(series(direction))
            self.assertEqual(D(d["rsi14"]),100 if direction>0 else 0)
            self.assertEqual(D(d["macd_12_26"]),D(7*direction))
            self.assertEqual(D(d["macd_histogram"]),0)
            self.assertEqual(D(d["atr14"]),2)
            zero="downside_semivariance_20" if direction>0 else "upside_semivariance_20"
            positive="upside_semivariance_20" if direction>0 else "downside_semivariance_20"
            self.assertEqual(D(d[zero]),0);self.assertGreater(D(d[positive]),0)
        with self.assertRaises(PilotError):m.indicators(series(1)[:-1])
    def test_fast_observation_and_time_validation(self):
        first=(NOW,D(100));second=(NOW+timedelta(seconds=30),D(101))
        d=m.fast_momentum(first,second)
        self.assertEqual(D(d["momentum_pct"]),1)
        self.assertFalse(d["continuous_path_verified"])
        for seconds in (0,20,32):
            with self.assertRaises(PilotError):m.fast_momentum(first,(NOW+timedelta(seconds=seconds),D(101)))
        raw={"symbol":"BTCUSDT","time":int(NOW.timestamp()*1000),"bidPrice":"99","askPrice":"101"}
        self.assertEqual(m.midpoint(raw,"BTCUSDT",NOW),first)
        for changes in ({"symbol":"ETHUSDT"},{"askPrice":"98"},{"time":raw["time"]-4000}):
            with self.assertRaises(PilotError):m.midpoint({**raw,**changes},"BTCUSDT",NOW)
    def test_bounded_candles_and_permission(self):
        calls=[]
        def transport(endpoint,p):
            calls.append((endpoint,p));self.assertEqual(endpoint,tf.KLINES)
            self.assertEqual(p["limit"],60)
            step=tf.FRAMES[p["interval"]];end=p["endTime"]+1
            return [[end-(60-i)*step,"100","101","99","100","100",
                     end-(59-i)*step-1,"10000",10,"50","5000","0"] for i in range(60)]
        with patch.dict(os.environ,ENV):
            d=m.run(transport=transport,clock=lambda:NOW)
            self.assertEqual(list(d["timeframes"]),["1m","5m"])
            self.assertEqual(len(calls),2)
            self.assertFalse(d["real_orders"]);self.assertFalse(d["pilot_applied"])
            self.assertIsNone(d["directional_signal"])
            calls.clear()
            with patch.dict(os.environ,{"CYBERBOT_FUTURES_MOMENTUM_ENABLED":"0"}):
                with self.assertRaises(PilotError):m.run(transport=transport,clock=lambda:NOW)
            self.assertEqual(calls,[])
    def test_fast_mode_only_two_book_requests(self):
        elapsed=[0];calls=[]
        def clock():return NOW+timedelta(seconds=elapsed[0])
        def sleep(seconds):elapsed[0]+=seconds
        def transport(endpoint,p):
            calls.append(endpoint);self.assertEqual(p,{"symbol":"BTCUSDT"})
            mid=100 if not elapsed[0] else 101
            return {"symbol":"BTCUSDT","time":int(clock().timestamp()*1000),
                    "bidPrice":str(mid-1),"askPrice":str(mid+1)}
        with patch.dict(os.environ,ENV):
            d=m.run(transport=transport,clock=clock,fast_probe=True,sleep=sleep,monotonic=lambda:elapsed[0])
        self.assertEqual(calls,[BOOK,BOOK])
        self.assertEqual(d["timeframes"],{})
        self.assertEqual(D(d["fast_momentum"]["momentum_pct"]),1)
        self.assertFalse(d["real_orders"])
