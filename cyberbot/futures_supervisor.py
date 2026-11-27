"""Bounded foreground Futures supervisor. Public observations and local PAPER only.

Single-threaded UTC slots, no catch-up bursts. A missed slot is not a
guaranteed execution opportunity. Do not run another writer on this pilot.
"""
import argparse,json,os,sqlite3,time
from contextlib import contextmanager
from datetime import timedelta
from . import futures_training as training,futures_forward_memory as forward
from . import futures_live_research as research,futures_auto_paper as auto
from . import futures_ai_bridge as bridge,futures_pilot as pilot
from . import observed_pilot as stocks,db_paths
from .providers import binance_observed as binance

VERSION="futures-supervisor-1"
MAX_MINUTES=1440
ERRORS=(ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error)

@contextmanager
def lease(kind="supervisor"):
    if kind not in ("supervisor","watchdog"):raise ValueError("Geçersiz süreç kilidi.")
    # OS advisory lease for supervisors sharing the pilot path; no stale PID lock.
    db_paths.checked()
    p=db_paths.pilot_path()
    lock=p.with_name(p.name+"."+kind+".lock")
    p.parent.mkdir(parents=True,exist_ok=True)
    with lock.open("a+b") as stream:
        if stream.seek(0,2)==0:stream.write(b"0");stream.flush()
        stream.seek(0)
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            try:yield
            finally:
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:yield
            finally:fcntl.flock(stream,fcntl.LOCK_UN)

def validate(symbol,minutes,paper,automatic):
    training.symbol_check(symbol)
    if type(minutes) is not int or not 1<=minutes<=MAX_MINUTES:
        raise ValueError("Oturum 1–1440 dakika.")
    if os.getenv("CYBERBOT_FUTURES_SUPERVISOR_ENABLED")!="1" or not research.permitted() or not forward.permitted():
        raise ValueError("Supervisor araştırma izinleri kapalı.")
    if automatic and not paper:raise ValueError("Otomatik mod için sanal gözlem gerekli.")
    if paper and (not pilot.enabled() or pilot.symbol()!=symbol or
        os.getenv("CYBERBOT_PILOT_INGRESS_ENABLED")!="1" or
        os.getenv("CYBERBOT_INGRESS_SOURCE_FUTURES")!=binance.SOURCE or
        os.getenv("CYBERBOT_FUTURES_SUPERVISOR_PAPER_CONFIRMED")!="1"):
        raise ValueError("Sanal gözlem izinleri kapalı.")
    if automatic and (not pilot.auto_enabled() or any(os.getenv(k)!="1" for k in bridge.FLAGS)):
        raise ValueError("Otomatik sanal giriş izinleri kapalı.")

def supervise(symbol,minutes,*,paper=False,automatic=False,clock=stocks.utc,sleep=time.sleep,emit=None):
    validate(symbol,minutes,paper,automatic)
    emit=emit or (lambda d:print(json.dumps(d,ensure_ascii=True,allow_nan=False),flush=True))
    last=clock()
    def now():
        nonlocal last
        t=clock()
        if t<last:raise ValueError("Yerel saat geriledi; oturum durdu.")
        last=t;return t
    def slot(at,grace):
        t=now()
        if t<at:sleep((at-t).total_seconds())
        t=now()
        return at<=t<=at+timedelta(seconds=grace)
    counts={"recorded":0,"missed":0,"paper_observations":0,"errors":0,"auto_intents":0}
    def report(stage,status,**kw):
        emit({"version":VERSION,"symbol":symbol,"at":now().isoformat(),"stage":stage,
              "status":status,"real_orders":False,**kw})
    def attempt(stage,fn):
        try:
            d=fn()
            report(stage,d.get("status","ok"))
            return d
        except ERRORS as exc:
            counts["errors"]+=1;report(stage,"rejected",error_type=type(exc).__name__)
            return None
    def observe(allow_auto=False):
        d=binance.run(apply=True,clock=now,auto_paper=allow_auto)
        if d.get("applied") is not True or d.get("real_orders") is not False:raise ValueError("Sanal gözlem geçersiz.")
        counts["paper_observations"]+=1
        return {"status":d["ingress"]["status"],"source_at":d["source_at"]}
    with lease():
        report("session","started")
        start=training.minute(now())+training.STEP
        pending_record=None
        last_observed=None
        # All slots advance by wall clock, never execute an old missed slot.
        for i in range(minutes):
            minute=start+i*training.STEP
            saved=None;prediction=None;queued=False
            if pending_record is not None and slot(minute,4):
                saved=attempt("training_save",lambda:training.save(pending_record,clock=now))
                if saved and saved["status"]=="recorded":counts["recorded"]+=1
                else:counts["missed"]+=1
            elif pending_record is not None:counts["missed"]+=1;report("training_save","missed_slot")
            pending_record=None
            if paper and slot(minute+timedelta(seconds=4),4):
                observed=attempt("paper_observe",observe)
                contiguous=bool(observed and last_observed and 0<(stocks.ts(observed["source_at"])-last_observed).total_seconds()<=30)
                last_observed=stocks.ts(observed["source_at"]) if observed else None
            else:
                contiguous=False
                if paper:last_observed=None;report("paper_observe","missed_slot")
            if saved and saved["status"]=="recorded" and now()<=minute+timedelta(seconds=18):
                prediction=attempt("forward",lambda:forward.tick(symbol,clock=now))
            # Reserve one minute out of 30 for offline research only when flat.
            # Never run CPU-heavy evaluation while a position or intent is active.
            research_minute=i%30==0
            if research_minute and saved and saved["status"]=="recorded" and now()<=minute+timedelta(seconds=15):
                state=attempt("paper_status",lambda:pilot.snapshot(clock=now)) if paper else {}
                if state is not None and not state.get("position") and not state.get("pending"):
                    attempt("research",lambda:research.evaluate_session(symbol,clock=now))
            elif automatic and contiguous and prediction and prediction["status"]=="recorded" and slot(minute+timedelta(seconds=19),3):
                d=attempt("auto_decision",lambda:auto.run(symbol,clock=now))
                queued=bool(d and d["status"]=="paper_intent_queued")
                if queued:counts["auto_intents"]+=1
            if paper and slot(minute+timedelta(seconds=30),4):
                # A late or failed decision cannot fill via a later normal observer.
                observed=attempt("paper_observe",lambda:observe(queued))
                last_observed=stocks.ts(observed["source_at"]) if observed else None
            elif paper:
                last_observed=None;report("paper_observe","missed_slot")
            if slot(minute+timedelta(seconds=40),4):
                pending_record=attempt("training_collect",lambda:{"status":"captured","record":training.collect(symbol,clock=now)})
                pending_record=pending_record["record"] if pending_record else None
                if pending_record is None:counts["missed"]+=1
            else:counts["missed"]+=1;report("training_collect","missed_slot")
            if paper and slot(minute+timedelta(seconds=55),2):
                observed=attempt("paper_observe",observe)
                last_observed=stocks.ts(observed["source_at"]) if observed else None
        if pending_record is not None and slot(start+minutes*training.STEP,4):
            saved=attempt("training_save",lambda:training.save(pending_record,clock=now))
            if saved and saved["status"]=="recorded":counts["recorded"]+=1
            else:counts["missed"]+=1
        elif pending_record is not None:counts["missed"]+=1
    return {"version":VERSION,"symbol":symbol,"status":"session_ended","minutes":minutes,"counts":counts,
            "paper_enabled":paper,"automatic_mode":automatic,"real_orders":False,
            "positions_may_remain_open":paper,"continuous_execution_verified":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"));p.add_argument("--minutes",type=int,default=1440)
    p.add_argument("--paper",action="store_true");p.add_argument("--automatic",action="store_true")
    a=p.parse_args()
    try:print(json.dumps(supervise(a.symbol,a.minutes,paper=a.paper,automatic=a.automatic),ensure_ascii=True));return 0
    except KeyboardInterrupt:return 130
    except ERRORS as exc:
        print(json.dumps({"status":"rejected","type":type(exc).__name__,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
