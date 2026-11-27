"""Offline tests for causal minute collection, retention and contiguous export."""
import os,unittest,tempfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from cyberbot import futures_training as t,db_paths,futures_lightgbm as batch
from cyberbot.providers import binance_observed as b,futures_timeframes as tf
START=datetime(2026,1,1,12,0,42,tzinfo=timezone.utc)
END=START.replace(second=0)+timedelta(minutes=1)

def response(endpoint,p,at=START):
    ms=int(at.timestamp()*1000);sym=p["symbol"]
    if endpoint==tf.KLINES:
        n=p["limit"];step=tf.FRAMES[p["interval"]];end=p["endTime"]+1
        return [[end-(n-i)*step,"100","101","99","100","100",
                 end-(n-i-1)*step-1,"10000",10,"60","6000","0"] for i in range(n)]
    if endpoint==b.BOOK:return {"symbol":sym,"time":ms,"bidPrice":"99","askPrice":"101","bidQty":"60","askQty":"40"}
    if endpoint==b.MARK:return {"symbol":sym,"time":ms,"markPrice":"100","indexPrice":"100","lastFundingRate":".0001"}
    if endpoint==b.OPEN_INTEREST:return {"symbol":sym,"time":ms,"openInterest":"500"}
    raise AssertionError(endpoint)

def fixture(at=START,sym="BTCUSDT"):
    record=t.collect(sym,clock=lambda:at,transport=lambda e,p:response(e,p,at))
    # Test persistence only with explicitly constructed fixture; no live data claim.
    return {**record,"transport_mocked":False}

class TrainingTests(unittest.TestCase):
    def setUp(self):
        root=tempfile.TemporaryDirectory();self.addCleanup(root.cleanup);self.root=Path(root.name)
        env={"CYBERBOT_DB":str(self.root/"paper.sqlite3"),"CYBERBOT_LEARNING_DB":str(self.root/"learn.sqlite3"),
             "CYBERBOT_WORKER_DB":str(self.root/"worker.sqlite3"),"CYBERBOT_PILOT_DB":str(self.root/"pilot.sqlite3"),
             "CYBERBOT_FUTURES_AI_MEMORY_DB":str(self.root/"memory.sqlite3"),
             "CYBERBOT_FUTURES_TRAINING_DB":str(self.root/"training.sqlite3"),
             "CYBERBOT_BINANCE_OBSERVED_ENABLED":"1","CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED":"1",
             "CYBERBOT_FUTURES_TRAINING_ENABLED":"1","CYBERBOT_EBBOT_DB":"","CYBERBOT_FX_FILE":""}
        self.env=env
        p=patch.dict(os.environ,env);p.start();self.addCleanup(p.stop)
    def test_five_requests_and_closed_cutoff(self):
        calls=[]
        def transport(e,p):calls.append((e,p));return response(e,p)
        d=t.collect("BTCUSDT",clock=lambda:START,transport=transport)
        self.assertEqual([e for e,p in calls],[tf.KLINES,tf.KLINES,b.BOOK,b.MARK,b.OPEN_INTEREST])
        self.assertEqual(d["row"]["at"],END.isoformat())
        self.assertEqual(d["row"]["taker_imbalance"],"0.2")
        self.assertEqual(d["row"]["book_imbalance"],"0.2")
        self.assertEqual(d["row"]["mid"],"100")
        self.assertEqual(d["candle_5m_end"],START.replace(second=0).isoformat())
        self.assertTrue(d["transport_mocked"])
        with self.assertRaises(ValueError):t.save(d,clock=lambda:END)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_reject_late_stale_and_missing_volume(self):
        def stale(e,p):
            data=response(e,p)
            if e==b.BOOK:data["time"]-=10000
            return data
        with self.assertRaises(ValueError):t.collect("BTCUSDT",clock=lambda:START,transport=stale)
        def volume(e,p):
            data=response(e,p)
            if e==tf.KLINES and p["interval"]=="5m":
                data[-1][5]=data[-1][9]="0"
            return data
        with self.assertRaises(ValueError):t.collect("BTCUSDT",clock=lambda:START,transport=volume)
        with self.assertRaises(ValueError):t.collect("BTCUSDT",clock=lambda:END,transport=lambda *a:self.fail("early network"))
        record=fixture()
        with self.assertRaises(ValueError):t.save(record,clock=lambda:START)
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_TRAINING_ENABLED":"0"}):
            with self.assertRaises(ValueError):t.collect("BTCUSDT",clock=lambda:START,transport=lambda *a:self.fail("disabled network"))
        self.assertEqual(list(self.root.iterdir()),[])
    def test_duplicate_gap_and_symbol_separation(self):
        self.assertEqual(t.status("BTCUSDT",clock=lambda:END)["contiguous_rows"],0)
        self.assertEqual(list(self.root.iterdir()),[])
        for i in (0,1,3,4):
            a=START+i*t.STEP;d=fixture(a)
            self.assertEqual(t.save(d,clock=lambda:a+t.STEP)["status"],"recorded")
        self.assertEqual(t.save(fixture(),clock=lambda:END)["status"],"duplicate_or_old")
        self.assertEqual(t.save(fixture(sym="ETHUSDT"),clock=lambda:END)["status"],"recorded")
        now=END+4*t.STEP
        self.assertEqual(t.status("BTCUSDT",clock=lambda:now)["contiguous_rows"],2)
        self.assertEqual(t.status("ETHUSDT",clock=lambda:now)["contiguous_rows"],1)
        with self.assertRaises(ValueError):t.export("BTCUSDT",clock=lambda:now)
    def test_valid_export_and_retention(self):
        for i in range(batch.MIN_ROWS):
            a=START+i*t.STEP;d=fixture(a)
            t.save(d,clock=lambda:a+t.STEP)
        now=END+batch.MIN_ROWS*t.STEP
        rows=t.export("BTCUSDT",clock=lambda:now)
        self.assertEqual(len(rows),batch.MIN_ROWS)
        self.assertEqual(set(rows[0]),batch.FIELDS)
        with patch.object(t,"KEEP",2):
            a=START+batch.MIN_ROWS*t.STEP
            t.save(fixture(a),clock=lambda:a+t.STEP)
        self.assertEqual(t.status("BTCUSDT",clock=lambda:now)["contiguous_rows"],2)
    def test_path_collision(self):
        with patch.dict(os.environ,{"CYBERBOT_FUTURES_TRAINING_DB":self.env["CYBERBOT_FUTURES_AI_MEMORY_DB"]}):
            with self.assertRaises(db_paths.PathCollision):t.save(fixture(),clock=lambda:END)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_foreground_cycle_scheduling(self):
        state=[START.replace(second=0)];calls=[]
        def clock():return state[0]
        def sleep(seconds):state[0]+=timedelta(seconds=seconds)
        def fake_collect(sym,*,clock):
            calls.append(clock())
            return records[clock()]
        records={START.replace(second=40)+i*t.STEP:fixture(START.replace(second=40)+i*t.STEP) for i in range(2)}
        with patch.object(t,"collect",side_effect=fake_collect):
            d=t.run("BTCUSDT",2,clock=clock,sleep=sleep)
        self.assertEqual([x.second for x in calls],[40,40])
        self.assertEqual([x["status"] for x in d["results"]],["recorded","recorded"])
