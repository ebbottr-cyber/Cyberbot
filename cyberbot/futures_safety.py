"""Read-only Futures connection and paper safety diagnostics. Never submit intents."""
import argparse,json,os,sqlite3,time
from contextlib import closing
from decimal import Decimal as D
from . import db_paths, futures_pilot as fut, observed_pilot as stocks
from . import futures_training as training, futures_ai_memory as memory
from .pilot_control import halted
from .operations import inspect_db
from .providers import binance_observed as binance

VERSION="futures-safety-1"
def status(symbol,*,clock=stocks.utc):
    training.symbol_check(symbol)
    now=clock()
    out={"version":VERSION,"symbol":symbol,"status":"read_only","as_of":now.isoformat(),
         "database_checks":{},"blockers":[],"paper_initialized":False,"entry_halted":None,
         "entry_gate":False,"quote_fresh":False,"funding_due":None,"position_open":False,
         "pending_side":None,"modeled_entry_budget_usdt":None,"network_probed":False,
         "automatic_entry_enabled":False,"real_orders":False}
    blockers=out["blockers"]
    db_paths.checked()
    paths={"paper_pilot":(db_paths.pilot_path(),{"observed_accounts","observed_events"}),
           "training":(db_paths.futures_training_path(),{training.TABLE}),
           "ai_memory":(db_paths.futures_ai_memory_path(),memory.TABLES)}
    for name,(p,tables) in paths.items():
        state=inspect_db(p,tables);out["database_checks"][name]=state
        if state not in ("ok","not_initialized"):blockers.append(name+"_database_"+state)
    if not binance.configured():blockers.append("binance_permissions")
    if not fut.enabled():blockers.append("paper_permissions")
    if fut.symbol()!=symbol:blockers.append("configured_paper_symbol_mismatch")
    if os.getenv("CYBERBOT_PILOT_INGRESS_ENABLED")!="1" or os.getenv("CYBERBOT_INGRESS_SOURCE_FUTURES")!=binance.SOURCE:
        blockers.append("ingress_permissions_or_source")
    p=paths["paper_pilot"][0]
    out["entry_halted"]=os.getenv("CYBERBOT_PILOT_KILL_SWITCH")=="1"
    if out["database_checks"]["paper_pilot"]=="ok":
        with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
            db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
            out["entry_halted"]=halted(db)
            if db.execute("SELECT 1 FROM observed_accounts WHERE market='FUTURES'").fetchone():
                s=fut.load(db,symbol);q=s["quote"];pos=s["position"];pending=s["pending"]
                fresh=fut.fresh(q,now)
                due=bool(pos and (int(now.timestamp())//fut.FUNDING_PERIOD>int(stocks.ts(q["source_at"]).timestamp())//fut.FUNDING_PERIOD))
                out.update(paper_initialized=True,quote_fresh=fresh,funding_due=due,position_open=bool(pos),
                           pending_side=pending["side"] if pending else None)
                if not fresh:blockers.append("stale_quote")
                if q and q.get("source")!=binance.SOURCE:blockers.append("paper_quote_source_mismatch")
                if due:blockers.append("funding_reconciliation_required")
                if pos or pending:blockers.append("position_or_pending")
                if fresh and not due and not pos and not pending:
                    if s.get("day")!=now.date().isoformat():blockers.append("daily_baseline_refresh_required")
                    else:
                        budget=fut.entry_risk_budget(s)
                        out["modeled_entry_budget_usdt"]=str(budget)
                        out["entry_gate"]=fut.entry_gate(q)
                        if budget<=0:blockers.append("capital_brake")
                        if not out["entry_gate"]:blockers.append("quote_entry_gate")
    if out["entry_halted"]:blockers.append("kill_switch")
    if not out["paper_initialized"]:blockers.append("paper_not_initialized")
    return out

def probe(symbol,*,clock=stocks.utc,sleep=time.sleep,transport=None):
    training.symbol_check(symbol)
    if os.getenv("CYBERBOT_FUTURES_SAFETY_PROBE_ENABLED")!="1" or not binance.configured():
        raise stocks.PilotError("Salt okunur bağlantı denetimi izni kapalı.")
    if fut.symbol()!=symbol:raise stocks.PilotError("Bağlantı sembolü uyuşmuyor.")
    before=clock();samples=[]
    for i in range(2):
        if i:sleep(3)
        d=binance.run(apply=False,clock=clock,transport=transport)
        now=clock()
        if not before<=now or (now-before).total_seconds()>45:raise stocks.PilotError("Bağlantı denetimi zaman sınırı.")
        if d.get("applied") is not False or d.get("real_orders") is not False or d.get("symbol")!=symbol:
            raise stocks.PilotError("Salt okunur yanıt uyuşmuyor.")
        q,_=fut.validate(d["quote"],now,symbol)
        if q["source"]!=binance.SOURCE:raise stocks.PilotError("Kaynak uyuşmuyor.")
        samples.append({"source_at":q["source_at"],"age_seconds":(now-stocks.ts(q["source_at"])).total_seconds(),
                        "entry_gate":fut.entry_gate(q)})
    advance=(stocks.ts(samples[1]["source_at"])-stocks.ts(samples[0]["source_at"])).total_seconds()
    valid=0<advance<=45
    return {"version":VERSION,"symbol":symbol,"status":"quotes_advanced" if valid else "quotes_not_advancing",
            "samples":samples,"source_advance_seconds":advance,"live_connection_sampled":valid and transport is None,
            "transport_mocked":transport is not None,"funding_schedule_accepted":True,
            "settled_funding_verified":False,"exchange_execution_verified":False,
            "paper_applied":False,"automatic_entry_enabled":False,"real_orders":False,
            "maximum_public_requests":6}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"))
    p.add_argument("--probe",action="store_true")
    a=p.parse_args()
    try:
        d=probe(a.symbol) if a.probe else status(a.symbol)
        print(json.dumps(d,ensure_ascii=False,allow_nan=False))
        return 1 if d["status"]=="quotes_not_advancing" else 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
