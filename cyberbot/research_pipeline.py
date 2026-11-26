"""Bounded offline research orchestration, content-addressed and per-market."""
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path
from .capital import CAPITAL,account_paths
from .learning import Journal,research
from .analysis import review
from .robustness import evaluate as robustness
from .regimes import evaluate as regimes,demo_rows
from .adaptive import evaluate as adaptive
from .tournament import tournament,TournamentJournal
from .strategy_memory import StrategyMemory,filter_choice
from .models import evaluate as models

VERSION="pipeline-1"

def research_path():
    p=Path(os.getenv("CYBERBOT_LEARNING_DB","var/learning.sqlite3")).expanduser().resolve()
    forbidden=set(account_paths().values())
    base=Path(os.getenv("CYBERBOT_DB","var/paper.sqlite3")).expanduser().resolve()
    forbidden.add((base.parent/(base.stem+"-markets")/"futures.sqlite3").resolve())
    forbidden.add(Path(os.getenv("CYBERBOT_DB","var/paper.sqlite3")).expanduser().resolve())
    forbidden.add(Path(os.getenv("CYBERBOT_WORKER_DB","var/worker.sqlite3")).expanduser().resolve())
    if os.getenv("CYBERBOT_EBBOT_DB"):forbidden.add(Path(os.environ["CYBERBOT_EBBOT_DB"]).expanduser().resolve())
    if p in forbidden or any(p.exists() and q.exists() and p.samefile(q) for q in forbidden):
        raise ValueError("Research database must be separate.")
    return p

def fingerprint(rows,mode,market,symbol):
    if not 240<=len(rows)<=1000:raise ValueError("240–1000 observations required.")
    canonical=[[str(D(str(x["open"])).normalize()),str(D(str(x["close"])).normalize()),x.get("session")] for x in rows]
    return hashlib.sha256(json.dumps([VERSION,mode,market,symbol,canonical],separators=(",",":")).encode()).hexdigest()

class PipelineJournal:
    def __init__(self,path):
        self.path=path
        Journal(path)
        with closing(sqlite3.connect(path,timeout=5)) as db,db:
            db.execute("CREATE TABLE IF NOT EXISTS research_pipeline(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,mode TEXT NOT NULL,market TEXT NOT NULL,symbol TEXT NOT NULL,payload TEXT NOT NULL)")
    def get(self,key):
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            row=db.execute("SELECT payload FROM research_pipeline WHERE id=?",(key,)).fetchone()
        return json.loads(row[0]) if row else None
    def save(self,result):
        with closing(sqlite3.connect(self.path,timeout=5)) as db,db:
            return bool(db.execute("INSERT OR IGNORE INTO research_pipeline VALUES(?,?,?,?,?,?)",(result["id"],datetime.now(timezone.utc).isoformat(),result["mode"],result["market"],result["symbol"],json.dumps(result,ensure_ascii=False,allow_nan=False))).rowcount)

def run(rows,*,mode,market,symbol):
    if market not in CAPITAL or mode not in ("synthetic","historical_unverified"):raise ValueError("Invalid market/mode.")
    path=research_path()
    journal=PipelineJournal(path)
    key=fingerprint(rows,mode,market,symbol)
    prior=journal.get(key)
    if prior is not None:
        return {"status":"duplicate","id":key,"market":market,"symbol":symbol,"summary":prior["summary"]}
    # Compute all stages before publishing any full experiment. Failed runs are not cached.
    a=review(symbol,rows,mode=mode,source="synthetic" if mode=="synthetic" else "local unverified archive")
    w=research(rows,mode=mode,symbol=market+":"+symbol)
    b=robustness(rows,mode=mode,market=market,symbol=symbol)
    t=tournament(rows,mode=mode,market=market,symbol=symbol)
    g=regimes(rows,mode=mode,market=market,symbol=symbol)
    s=adaptive(rows,mode=mode,market=market,symbol=symbol)
    m=models([row["close"] for row in rows],mode=mode)
    Journal(path).save(w)
    TournamentJournal(path).save(t)
    mem=StrategyMemory(path).record(s)
    s["memory"]=mem
    s["next_research_candidate"]=filter_choice(s["next_research_candidate"],mem["states"])
    summary={"regime":g["next_observation_regime"]["id"],"tournament_status":t["status"],
             "research_champion":t["research_champion"],"next_candidate":s["next_research_candidate"]["strategy"],
             "shadow_return_pct":s["shadow"]["return_pct"],"shadow_drawdown_pct":s["shadow"]["drawdown_pct"],
             "quarantined":[k for k,v in mem["states"].items() if v["status"]=="quarantined"],
             "new_evidence":mem["accepted"],"stages":7}
    result={"id":key,"version":VERSION,"mode":mode,"market":market,"symbol":symbol,"summary":summary,
            "analysis":a,"walkforward":w,"robustness":b,"tournament":t,"regimes":g,"adaptive":s,"models":m,
            "real_orders":False,"paper_orders":False,"promotion_enabled":False,"profitability_verified":False}
    inserted=journal.save(result)
    return {"status":"new" if inserted else "duplicate","id":key,"market":market,"symbol":symbol,"summary":summary}

def demo_jobs():
    for market in CAPITAL:
        yield market,"DEMO-ADAPTIVE-"+market,demo_rows(market)
