"""Bounded local Futures diagnostic journal and read-only health summary."""
import argparse,json,os,sqlite3
from collections import Counter
from contextlib import closing
from datetime import timedelta
from . import db_paths,observed_pilot as stocks,futures_training as training
from . import futures_forward_memory as forward,futures_ai_memory as memory
from . import futures_safety as safety
from .operations import inspect_db

VERSION="futures-health-1"
TABLE="futures_diagnostics_v1"
KEEP=10000
STAGES={"session","training_save","training_collect","paper_observe","forward","research","paper_status","auto_decision","watchdog"}
STATUSES=set("started captured recorded duplicate_or_old missed_slot rejected ok waiting_for_data waiting_for_target stale_features overlapping_target forecast_expired duplicate_or_overlapping waiting_for_contiguous_data stale_training_data waiting_for_new_test_window concurrent_or_overlapping_evidence research_completed observation open_fill close_fill entry_cancelled expired entry_rejected exit_waiting_depth model_liquidation position_or_pending waiting_for_forward_evidence memory_veto ai_disagreement_or_hold risk_veto paper_intent_queued child_start child_end recovery_backoff session_ended completed interrupted session_deadline restart_limit_reached".split())
REASONS=set("heartbeat_timeout invalid_child_event child_exit_without_completion child_stdout_closed child_start_or_stop_error training_collect_unhealthy paper_observe_unhealthy completed interrupted session_deadline".split())
ERROR_TYPES=set("ValueError OSError ArithmeticError KeyError TypeError Error OperationalError DatabaseError IntegrityError ResearchError PilotError PathCollision TimeoutError OverflowError".split())
ERRORS=(ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error)
def enabled():return os.getenv("CYBERBOT_FUTURES_DIAGNOSTICS_ENABLED")=="1"
def path():
    db_paths.checked();return db_paths.futures_diagnostics_path()
def schema(db,create=False):
    names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
    if names and names!={TABLE}:raise ValueError("Teşhis şeması uyuşmuyor.")
    if not names and create:
        db.execute("CREATE TABLE "+TABLE+"(id INTEGER PRIMARY KEY,symbol TEXT NOT NULL,at TEXT NOT NULL,stage TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL)")
    return bool(names) or create
def clean(event,now):
    if not isinstance(event,dict) or event.get("real_orders") is not False:raise ValueError("Teşhis olayı geçersiz.")
    sym=event["symbol"];training.symbol_check(sym)
    v=event.get("version")
    if v not in ("futures-supervisor-1","futures-watchdog-1"):raise ValueError("Teşhis sürümü geçersiz.")
    stage="watchdog" if v=="futures-watchdog-1" else event.get("stage","session")
    if not isinstance(stage,str) or stage not in STAGES:stage="session"
    status=event.get("status")
    if not isinstance(status,str) or status not in STATUSES:status="other"
    payload={}
    for k,allowed in (("reason",REASONS),("error_type",ERROR_TYPES)):
        if isinstance(event.get(k),str) and event[k] in allowed:payload[k]=event[k]
    for k,maximum in (("attempt",4),("seconds",150),("restarts",3)):
        if type(event.get(k)) is int and 0<=event[k]<=maximum:payload[k]=event[k]
    for k in ("automatic_mode","recovery_entry_brake","paper_enabled","positions_may_remain_open"):
        if type(event.get(k)) is bool:payload[k]=event[k]
    return sym,now.isoformat(),stage,status,json.dumps(payload,separators=(",",":"))
def record(event,*,clock=stocks.utc):
    if not enabled():raise ValueError("Teşhis izni kapalı.")
    row=clean(event,clock());p=path();p.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(p,timeout=2,isolation_level=None)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            schema(db,True)
            db.execute("INSERT INTO "+TABLE+"(symbol,at,stage,status,payload) VALUES(?,?,?,?,?)",row)
            db.execute("DELETE FROM "+TABLE+" WHERE symbol=? AND id NOT IN (SELECT id FROM "+TABLE+" WHERE symbol=? ORDER BY id DESC LIMIT ?)",(row[0],row[0],KEEP))
            db.commit()
        except BaseException:db.rollback();raise
def sink(event):
    if enabled():
        try:record(event)
        except ERRORS as exc:
            print(json.dumps({"version":VERSION,"status":"diagnostic_write_failed","error_type":type(exc).__name__,"real_orders":False}),flush=True)
    print(json.dumps(event,ensure_ascii=True,allow_nan=False),flush=True)
def journal(symbol,*,clock=stocks.utc):
    training.symbol_check(symbol);now=clock();p=path();rows=[]
    if p.is_file():
        with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=2)) as db:
            db.execute("PRAGMA query_only=ON")
            if schema(db):rows=db.execute("SELECT at,stage,status,payload FROM "+TABLE+" WHERE symbol=? ORDER BY id DESC LIMIT ?",(symbol,KEEP)).fetchall()
    recent=[{"at":at,"stage":stage,"status":status,**json.loads(payload)} for at,stage,status,payload in rows]
    day=[e for e in recent if now-timedelta(days=1)<=stocks.ts(e["at"])<=now]
    last=recent[0]["at"] if recent else None
    age=(now-stocks.ts(last)).total_seconds() if last else None
    return {"retained":len(recent),"last_event_at":last,"last_event_age_seconds":age,
            "activity":"recent_events" if age is not None and 0<=age<=150 else "stale_or_no_events",
            "process_running_verified":False,"last_24h_counts":dict(Counter(e["stage"]+":"+e["status"] for e in day)),
            "restart_attempts_24h":sum(e["stage"]=="watchdog" and e["status"]=="recovery_backoff" for e in day),
            "recent":recent[:30]}
def health(symbol,*,clock=stocks.utc):
    training.symbol_check(symbol);now=clock()
    out={"version":VERSION,"symbol":symbol,"as_of":now.isoformat(),"status":"read_only","component_errors":{},
         "real_orders":False,"network_probed":False,"process_running_verified":False}
    def read(name,fn):
        try:out[name]=fn()
        except ERRORS as e:out["component_errors"][name]=type(e).__name__;out[name]=None
    read("journal",lambda:journal(symbol,clock=lambda:now))
    read("training",lambda:training.status(symbol,clock=lambda:now))
    read("forward",lambda:forward.snapshot(symbol))
    read("ai_memory",lambda:{"states":memory.snapshot(symbol)["states"]})
    read("paper_safety",lambda:safety.status(symbol,clock=lambda:now))
    read("database_checks",lambda:{"diagnostics":inspect_db(path(),{TABLE}),"forward":inspect_db(forward.path(),{forward.TABLE})})
    checks=dict(out["database_checks"] or {})
    if out["paper_safety"]:checks.update(out["paper_safety"]["database_checks"])
    out["status"]="degraded" if out["component_errors"] or any(v not in ("ok","not_initialized") for v in checks.values()) else "read_only"
    return out
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"));a=p.parse_args()
    print(json.dumps(health(a.symbol),ensure_ascii=True,allow_nan=False));return 0
if __name__=="__main__":raise SystemExit(main())
