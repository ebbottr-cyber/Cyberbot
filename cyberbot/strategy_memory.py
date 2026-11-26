"""Chronological research evidence and quarantine. No execution authority."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path

VERSION="memory-1"
CANDIDATES=("trend","momentum","reversion")

def initial():
    return {"status":"observing","loss_streak":0,"recovery_streak":0,"blocks":0,"last_end":None,"reason":"no_evidence"}

def update(state,block):
    s=dict(state)
    s["blocks"]+=1
    s["last_end"]=block["end_key"]
    severe=max(block["drawdown_pct"],block["double_cost_drawdown_pct"])>10
    active=block["closed_trades"]>0
    good=active and block["return_pct"]>0 and block["double_cost_return_pct"]>0 and not severe
    bad=active and (block["return_pct"]<0 or block["double_cost_return_pct"]<0)
    if severe:
        s.update(status="quarantined",reason="drawdown_limit",loss_streak=0,recovery_streak=0)
    elif s["status"]=="quarantined":
        s["recovery_streak"]=s["recovery_streak"]+1 if good else 0
        if s["recovery_streak"]>=3:
            s.update(status="observing",reason="three_recovery_blocks",loss_streak=0,recovery_streak=0)
    elif active:
        s["loss_streak"]=s["loss_streak"]+1 if bad else 0
        if s["loss_streak"]>=2:
            s.update(status="quarantined",reason="two_losing_blocks",recovery_streak=0)
    return s

def filter_choice(choice,states):
    ranking=[]
    for row in choice["ranking"]:
        s=states.get(row["strategy"],initial())
        ranking.append({**row,"quarantine_status":s["status"],"eligible":row["eligible"] and s["status"]!="quarantined"})
    eligible=[x for x in ranking if x["eligible"]]
    return {**choice,"ranking":ranking,"strategy":eligible[0]["strategy"] if eligible else "cash",
            "reason":"shadow_candidate" if eligible else "insufficient_weak_or_quarantined"}

class StrategyMemory:
    def __init__(self,path):
        self.path=Path(path)
        with closing(sqlite3.connect(self.path,timeout=5)) as db,db:
            db.execute("CREATE TABLE IF NOT EXISTS strategy_memory(scope TEXT NOT NULL,strategy TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(scope,strategy))")
            db.execute("CREATE TABLE IF NOT EXISTS strategy_evidence(scope TEXT NOT NULL,strategy TEXT NOT NULL,start_key TEXT NOT NULL,end_key TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(scope,strategy,start_key,end_key))")
    def scope(self,mode,market,symbol):
        return json.dumps([VERSION,mode,market,symbol],ensure_ascii=False,separators=(",",":"))
    def record(self,result):
        scope=self.scope(result["mode"],result["market"],result["symbol"])
        accepted=skipped=0
        with closing(sqlite3.connect(self.path,timeout=10,isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            states={}
            for name in CANDIDATES:
                row=db.execute("SELECT payload FROM strategy_memory WHERE scope=? AND strategy=?",(scope,name)).fetchone()
                states[name]=json.loads(row[0]) if row else initial()
            for block in result["evidence_blocks"]:
                name=block["strategy"];s=states[name]
                # Strictly forward, non-overlapping evidence. Corrections/replays do not
                # erase prior failures or count as new evidence.
                if s["last_end"] is not None and block["start_key"]<=s["last_end"]:
                    skipped+=1;continue
                if block["end_key"]<block["start_key"]:raise ValueError("Invalid evidence interval.")
                s=update(s,block);states[name]=s
                db.execute("INSERT INTO strategy_evidence VALUES(?,?,?,?,?,?)",(scope,name,block["start_key"],block["end_key"],json.dumps({"block":block,"state":s},ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
                db.execute("INSERT OR REPLACE INTO strategy_memory VALUES(?,?,?)",(scope,name,json.dumps(s,ensure_ascii=False)))
                accepted+=1
            db.commit()
        return {"accepted":accepted,"skipped":skipped,"states":states,"promotion_enabled":False}
    def read(self,mode,market,symbol):
        scope=self.scope(mode,market,symbol)
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            states={name:initial() for name in CANDIDATES}
            states.update({name:json.loads(payload) for name,payload in db.execute("SELECT strategy,payload FROM strategy_memory WHERE scope=?",(scope,))})
            rows=db.execute("SELECT payload,created_at FROM strategy_evidence WHERE scope=? ORDER BY rowid DESC LIMIT 30",(scope,)).fetchall()
        return {"states":states,"recent":[{**json.loads(p),"created_at":t} for p,t in rows],"promotion_enabled":False,"real_orders":False}
