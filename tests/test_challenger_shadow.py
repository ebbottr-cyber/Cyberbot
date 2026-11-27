"""Synthetic prospective trial checks, without native models or trading."""
from datetime import datetime,timedelta,timezone
import json
import sqlite3
import unittest
from tools.local_research.challenger_shadow import tick,summarize,minute,SCOPE

CID="a"*64


class ChallengerTests(unittest.TestCase):
    def setUp(self):
        self.src=sqlite3.connect(":memory:")
        self.db=sqlite3.connect(":memory:")
        self.addCleanup(self.src.close)
        self.addCleanup(self.db.close)
        self.src.execute("""CREATE TABLE forecasts (market TEXT,symbol TEXT,source TEXT,
            target_minute INTEGER,created_at TEXT,payload TEXT,status TEXT,outcome TEXT)""")
        self.t=datetime(2020,1,1,12,0,20,tzinfo=timezone.utc)
        self.assertEqual(tick(self.src,self.db,CID,lambda x:.1,now=lambda:self.t),"TRIAL_REGISTERED")

    def add(self,t):
        p={"mode":"forward_shadow_research","context_bars":21,"prediction_bars":1,
           "automatic_promotion":False,"real_orders":False,"last_price":100,
           "predictions":{"naive":0.,"mean":.02,"ar1":.04,"chronos":.08}}
        self.src.execute("INSERT INTO forecasts VALUES (?,?,?,?,?,?,?,?)",
            (*SCOPE,minute(t),(t-timedelta(seconds=5)).isoformat(),json.dumps(p),"pending",None))
        self.src.commit()

    def settle(self,t):
        o={"target_source_at":(t+timedelta(seconds=30)).isoformat(),
           "actual_return_pct":.1,"execution_verified":False,"real_orders":False,
           "absolute_errors_pct":{"naive":.1,"mean":.08,"ar1":.06,"chronos":.02}}
        self.src.execute("UPDATE forecasts SET status='measured',outcome=? WHERE target_minute=?",
                         (json.dumps(o),minute(t)))
        self.src.commit()

    def test_registration_before_first_target_and_frozen_candidate(self):
        self.add(self.t)
        self.assertEqual(tick(self.src,self.db,CID,lambda x:.1,now=lambda:self.t),"WAIT_WINDOW")
        with self.assertRaises(ValueError):
            tick(self.src,self.db,"b"*64,lambda x:.1,now=lambda:self.t)

    def test_prospective_only_and_duplicate(self):
        t=self.t+timedelta(minutes=1)
        self.add(t)
        self.assertEqual(tick(self.src,self.db,CID,lambda x:.1,now=lambda:t),"FORECAST_RECORDED")
        self.assertEqual(tick(self.src,self.db,CID,lambda x:.1,now=lambda:t),"ALREADY_RECORDED_OR_CLOCK_REVIEW")
        self.settle(t)
        r=summarize(self.src,self.db,now=t+timedelta(minutes=1))
        self.assertEqual(r["counts"]["retained"],1)
        self.assertEqual(r["status"],"INSUFFICIENT_EVIDENCE")
        self.assertEqual(r["daily_weighted_mae_pct"]["lightgbm"],0)
        self.assertFalse(r["automatic_promotion"])

    def test_measured_source_never_backfilled(self):
        t=self.t+timedelta(minutes=1)
        self.add(t)
        self.settle(t)
        self.assertEqual(tick(self.src,self.db,CID,lambda x:self.fail("no backfill"),now=lambda:t),"WAIT_SOURCE")

    def test_expired_window_rolls_back(self):
        t=self.t+timedelta(minutes=1)
        self.add(t)
        stamps=iter((t,t+timedelta(seconds=16)))
        self.assertEqual(tick(self.src,self.db,CID,lambda x:.1,now=lambda:next(stamps)),"WINDOW_EXPIRED")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0],0)

    def test_source_change_detected(self):
        t=self.t+timedelta(minutes=1)
        self.add(t)
        tick(self.src,self.db,CID,lambda x:.1,now=lambda:t)
        self.src.execute("UPDATE forecasts SET payload='{}'")
        with self.assertRaises(ValueError):
            summarize(self.src,self.db,now=t)

    def test_review_requires_ten_days_and_sixty_blocks(self):
        for day in range(1,11):
            for i in range(6):
                t=self.t+timedelta(days=day,minutes=22*i)
                self.add(t)
                tick(self.src,self.db,CID,lambda x:.1,now=lambda:t)
                self.settle(t)
        r=summarize(self.src,self.db,now=t+timedelta(minutes=1))
        self.assertEqual(r["status"],"REVIEW_ONLY")
        self.assertEqual(r["counts"]["retained"],60)
        self.assertFalse(r["paper_readiness_verified"])
