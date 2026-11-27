"""Offline tests for fail-closed Futures consensus and shared candle requests."""
import os,unittest
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cyberbot.providers import futures_consensus as c,futures_timeframes as tf
from cyberbot.providers import futures_sentiment as s,binance_observed as b
from cyberbot.observed_pilot import PilotError

NOW=datetime(2026,1,1,12,2,tzinfo=timezone.utc)
SYM="BTCUSDT"
CUTOFF=int(NOW.timestamp()*1000)-3000
BASE={"symbol":SYM,"status":"research_only","real_orders":False,"pilot_applied":False,"directional_signal":None}
ENV={"CYBERBOT_BINANCE_OBSERVED_ENABLED":"1","CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1",
     "CYBERBOT_FUTURES_CONSENSUS_ENABLED":"1","CYBERBOT_FUTURES_TIMEFRAMES_ENABLED":"1",
     "CYBERBOT_FUTURES_MOMENTUM_ENABLED":"1","CYBERBOT_FUTURES_PILOT_SYMBOL":SYM}
def fixture():
    frames={f:{"closed_through":b.stamp(CUTOFF//step*step).isoformat(),"closed_bars":21,"trend_label":"UP"}
            for f,step in tf.FRAMES.items()}
    metrics={f:{"closed_through":frames[f]["closed_through"],"closed_bars":60,"rsi14":"60",
                "macd_histogram":"1","momentum_5_bars_pct":"1","atr_pct":".5",
                "upside_semivariance_20":".001","downside_semivariance_20":".0001"}
             for f in ("1m","5m")}
    return {"symbol":SYM,"now":NOW,
            "market":{**BASE,"source_at":NOW.isoformat(),"mark_index_basis_pct":".01",
                      "reported_last_funding_rate":".0001","open_interest_base":"500"},
            "book":{**BASE,"status":"visible_snapshot_only","source_at":NOW.isoformat(),
                    "ticker_top_matches":True,"spread_bps":"1",
                    "depth_bands":[{"levels_per_side":n,"notional_imbalance":".2"} for n in (5,10,20)]},
            "timeframes":{**BASE,"cutoff_at":b.stamp(CUTOFF).isoformat(),"timeframes":frames},
            "momentum":{**BASE,"mode":"closed_candles","timeframes":metrics},
            "sentiment":{**BASE,"period":"5m","period_end":(NOW-timedelta(minutes=2)).isoformat(),
                         "taker_volume":{"volume_imbalance":".2"},"global_accounts":{"long_share":".6"}}}

class ConsensusTests(unittest.TestCase):
    def test_alignment_never_authorizes_orders(self):
        d=c.evaluate(**fixture())
        self.assertEqual(d["research_label"],"research_up")
        self.assertEqual(set(d["votes"].values()),{"UP"})
        self.assertEqual(d["actual_action"],"HOLD")
        for flag in ("real_orders","paper_orders","pilot_applied","thresholds_validated","independent_sources_verified"):
            self.assertIs(d[flag],False)
        self.assertIsNone(d["confidence_probability"])
        self.assertEqual(d["optional_context"]["liquidations"],"not_provided")

    def test_conflicts_and_risk_vetoes(self):
        a=fixture();a["timeframes"]["timeframes"]["4h"]["trend_label"]="DOWN"
        self.assertEqual(c.evaluate(**a)["research_label"],"HOLD")
        a=fixture();a["book"]["depth_bands"].pop()
        self.assertIn("book_incomplete_or_top_mismatch",c.evaluate(**a)["blockers"])
        a=fixture();a["market"]["reported_last_funding_rate"]=".005"
        self.assertIn("elevated_reported_funding",c.evaluate(**a)["blockers"])
        a=fixture();a["sentiment"]["global_accounts"]["long_share"]=".9"
        self.assertEqual(c.evaluate(**a)["research_label"],"HOLD")
        a=fixture();a["momentum"]["timeframes"]["1m"]["atr_pct"]="3"
        self.assertIn("elevated_atr",c.evaluate(**a)["blockers"])

    def test_invalid_identity_time_and_safety_fields(self):
        for field,change in (("market",{"symbol":"ETHUSDT"}),
                             ("book",{"source_at":(NOW-timedelta(seconds=31)).isoformat()}),
                             ("sentiment",{"period_end":(NOW+timedelta(seconds=1)).isoformat()}),
                             ("momentum",{"real_orders":True})):
            a=fixture();a[field].update(change)
            with self.assertRaises(PilotError):c.evaluate(**a)
        a=fixture();a["momentum"]["timeframes"]["5m"]["closed_through"]=NOW.isoformat()
        with self.assertRaises(PilotError):c.evaluate(**a)

    def test_optional_context_is_veto_not_proof(self):
        a=fixture()
        fast={**BASE,"mode":"30s_midpoint","fast_momentum":{"start_at":(NOW-timedelta(seconds=30)).isoformat(),
              "end_at":NOW.isoformat(),"momentum_pct":"-.2"}}
        liq={**BASE,"status":"snapshot_window_complete","ended_at":NOW.isoformat(),
             "window_complete":True,"clusters":[{"side":"LONG"}]}
        result=c.evaluate(**a,fast=fast,liquidations=liq)
        self.assertEqual(result["research_label"],"HOLD")
        self.assertIn("fast_momentum_not_confirming",result["blockers"])
        self.assertIn("liquidation_cluster_observed",result["blockers"])
        liq["window_complete"]=False
        with self.assertRaises(PilotError):c.evaluate(**a,liquidations=liq)

    def test_shared_candle_requests_and_permissions(self):
        calls=[];ms=int(NOW.timestamp()*1000);end=ms//300000*300000
        def transport(endpoint,p):
            calls.append((endpoint,p))
            if endpoint==tf.KLINES:
                step=tf.FRAMES[p["interval"]];n=p["limit"];e=p["endTime"]+1
                return [[e-(n-i)*step,"100","101","99","100","100",e-(n-i-1)*step-1,
                         "10000",10,"50","5000","0"] for i in range(n)]
            if endpoint==s.GLOBAL:return [{"symbol":SYM,"timestamp":end,"longAccount":".6","shortAccount":".4","longShortRatio":"1.5"}]
            if endpoint==s.TAKER:return [{"timestamp":end-300000,"buyVol":"60","sellVol":"40","buySellRatio":"1.5"}]
            if endpoint==b.INFO:return []
            if endpoint==b.BOOK:return {"symbol":SYM,"time":ms,"bidPrice":"99.99","askPrice":"100.01","bidQty":"10","askQty":"10"}
            if endpoint==b.MARK:return {"symbol":SYM,"time":ms,"markPrice":"100","indexPrice":"100",
                                       "lastFundingRate":".0001","nextFundingTime":(ms//b.PERIOD_MS+1)*b.PERIOD_MS}
            if endpoint==b.OPEN_INTEREST:return {"symbol":SYM,"time":ms,"openInterest":"500"}
            if endpoint==b.DEPTH:return {"lastUpdateId":1,"E":ms,"T":ms,"bids":[["99.99","10"]],"asks":[["100.01","10"]]}
            self.fail(endpoint)
        with patch.dict(os.environ,ENV):
            d=c.run(transport=transport,clock=lambda:NOW)
            self.assertEqual(d["research_label"],"HOLD")
            self.assertEqual(len(calls),12)
            self.assertEqual([p["limit"] for e,p in calls if e==tf.KLINES],[60,60,21,21,21])
            self.assertTrue(d["transport_mocked"])
            calls.clear()
            with patch.dict(os.environ,{"CYBERBOT_FUTURES_CONSENSUS_ENABLED":"0"}):
                with self.assertRaises(PilotError):c.run(transport=transport,clock=lambda:NOW)
            self.assertEqual(calls,[])
