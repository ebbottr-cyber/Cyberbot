"""Opt-in local research worker. Never calls paper mutations, LLMs or network."""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from .operations import health,backup,sources
from .learning import Journal,demo_rows,research
from .providers.equity import history

def now():
    return datetime.now(timezone.utc).isoformat()

def worker_path():
    p=Path(os.getenv("CYBERBOT_WORKER_DB","var/worker.sqlite3")).expanduser().resolve()
    excluded=set(sources().values())
    if os.getenv("CYBERBOT_EBBOT_DB"):
        excluded.add(Path(os.environ["CYBERBOT_EBBOT_DB"]).expanduser().resolve())
    if p in excluded:raise ValueError("Worker database must be separate.")
    return p

def status():
    empty={"status":"not_started","last_cycle":None,"cycles_recorded":0,"recent":[],"real_orders":False}
    try:
        p=worker_path()
        if not p.is_file():return empty
        with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=1)) as db:
            rows=db.execute("SELECT payload FROM cycles ORDER BY id DESC LIMIT 20").fetchall()
            recent=[json.loads(r[0]) for r in rows]
            count=db.execute("SELECT count(*) FROM cycles").fetchone()[0]
        return {**empty,"status":"recorded" if recent else "not_started","last_cycle":recent[0] if recent else None,"cycles_recorded":count,"recent":recent}
    except (OSError,sqlite3.Error,ValueError,TypeError):
        return {**empty,"status":"unavailable"}

def run_cycle(*,market=None,symbol=None,backup_daily=False):
    if bool(market)!=bool(symbol):raise ValueError("Market and symbol must be supplied together.")
    p=worker_path()
    p.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(p,timeout=1,isolation_level=None)) as db:
        try:
            db.execute("CREATE TABLE IF NOT EXISTS cycles(id INTEGER PRIMARY KEY,payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():return {"status":"busy","real_orders":False}
            raise
        started=now()
        report={"started_at":started,"mode":"historical_unverified" if market else "synthetic",
                "status":"ok","experiment":"not_run","backup":"not_requested","real_orders":False,"promotion_enabled":False}
        try:
            report["health"]=health()["status"]
            if report["health"]!="ok":
                report["status"]="degraded"
            else:
                if market:
                    data=history(os.getenv("CYBERBOT_EBBOT_DB"),market,symbol,250)
                    result=research(data["bars"],mode="historical_unverified",symbol=market+":"+symbol)
                else:
                    result=research(demo_rows(),mode="synthetic",symbol="DEMO-WALK")
                journal=Journal(sources()["learning"])
                report["experiment"]="new" if journal.save(result) else "duplicate"
                report["experiment_id"]=result["id"]
                if backup_daily:
                    key=started[:10]
                    prior=db.execute("SELECT value FROM settings WHERE key='backup_day'").fetchone()
                    if prior and prior[0]==key:report["backup"]="already_done"
                    else:
                        backup(Path("var/backups"))
                        db.execute("INSERT OR REPLACE INTO settings VALUES('backup_day',?)",(key,))
                        report["backup"]="created"
        except Exception as e:
            report["status"]="failed"
            report["error_type"]=type(e).__name__
        report["finished_at"]=now()
        db.execute("INSERT INTO cycles(payload) VALUES (?)",(json.dumps(report,ensure_ascii=False),))
        # Bounded operational journal, not the research journal.
        db.execute("DELETE FROM cycles WHERE id NOT IN (SELECT id FROM cycles ORDER BY id DESC LIMIT 1000)")
        db.commit()
        return report
