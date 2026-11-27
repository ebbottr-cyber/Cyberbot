"""Causal, opt-in observed-minute shadow decisions. Never requests any order."""
import os,json,sqlite3,hashlib
from contextlib import closing
from datetime import datetime,timezone
from decimal import Decimal as D
from . import observed_pilot as stocks,solana_pilot as sol,futures_pilot as fut
from .strategy_lab import signal
from .regimes import classify
from .observed_regime import diagnose
from .research_pipeline import research_path
from .strategy_memory import VERSION as MEMORY_VERSION
from .observed_pilot import PilotError,ts
from .pilot_control import halted

VERSION="pilot-shadow-2"
MARKETS=("BIST","NASDAQ","XETRA","SOLANA","FUTURES")
WINDOW=10
MINUTES=21
MAX_ROWS=3000
CANDIDATES=("trend","momentum","reversion")
def enabled():
    return stocks.permitted() and os.getenv("CYBERBOT_PILOT_SHADOW_ENABLED")=="1"
def market_enabled(m):
    return enabled() and (stocks.fx_permitted() if m=="XETRA" else sol.enabled() if m=="SOLANA" else fut.enabled() if m=="FUTURES" else True)
def state(db,m):
    if not db.execute("SELECT 1 FROM observed_accounts WHERE market=?",(m,)).fetchone():return None,None
    if m=="SOLANA":
        mint,pool=sol.config();return sol.load(db,mint,pool),mint
    if m=="FUTURES":
        sym=fut.symbol();return fut.load(db,sym),sym
    return stocks.load(db,m),stocks.account(m)[0]
def context(m,symbol,now):
    # Previous incompatible timeframes/modes are context only, never promotion evidence.
    p=research_path();out=[]
    if not p.is_file():return out
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
        tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "research_pipeline" not in tables:return out
        for mode in ("historical_unverified","synthetic"):
            row=db.execute("SELECT id,created_at,payload FROM research_pipeline WHERE market=? AND symbol=? AND mode=? ORDER BY created_at DESC,id DESC LIMIT 1",(m,symbol,mode)).fetchone()
            if not row:continue
            key,at,payload=row;d=json.loads(payload)
            if ts(at)>now or (d.get("id"),d.get("market"),d.get("symbol"),d.get("mode"))!=(key,m,symbol,mode):continue
            quarantine=[]
            if "strategy_memory" in tables:
                scope=json.dumps([MEMORY_VERSION,mode,m,symbol],ensure_ascii=False,separators=(",",":"))
                quarantine=[n for n,payload in db.execute("SELECT strategy,payload FROM strategy_memory WHERE scope=?",(scope,)) if n in CANDIDATES and json.loads(payload).get("status")=="quarantined"]
            out.append({"id":key,"mode":mode,"created_at":at,"research_candidate":d.get("summary",{}).get("next_candidate"),"quarantined":sorted(quarantine),"compatible_evidence":False})
    return out
def completed_minutes(db,m,q,now):
    current=int(now.timestamp()//60);want=list(range(current-MINUTES,current));values={}
    # Restrict to actual observation rows; requests/decisions never become price samples.
    rows=db.execute("SELECT at,payload FROM observed_events WHERE market=? AND event!='request' AND event!='shadow_decision' ORDER BY id DESC LIMIT ?",(m,MAX_ROWS)).fetchall()
    for recorded,payload in rows:
        d=json.loads(payload);v=d.get("quote")
        if not v or v.get("source")!=q["source"] or v.get("venue")!=q.get("venue"):continue
        t=ts(v["source_at"]);received=ts(recorded);minute=int(t.timestamp()//60)
        if minute not in want or minute in values or not t<=received<=now or (received-t).total_seconds()>30 or t.second<45:continue
        bid,ask=D(v["bid"]),D(v["ask"])
        if not bid.is_finite() or not ask.is_finite() or not 0<bid<=ask:raise PilotError("Geçersiz gözlem.")
        # Native quote-currency midpoint. These are sampled observations, not exchange OHLC closes.
        values[minute]=(bid+ask)/2
    if any(k not in values for k in want):return [],len(values)
    return [values[k] for k in want],len(values)
def evaluate(db,m,now):
    d={"version":VERSION,"market":m,"as_of":now.isoformat(),"minute":int(now.timestamp()//60),"mode":"shadow_only","status":"no_observation","symbol":None,"observations":0,"regime":None,"signals":{},"research_context":[],"candidate":"cash","hypothetical_action":"HOLD","actual_action":"HOLD","blockers":["no_compatible_observed_minute_forward_evidence","automatic_entry_disabled"],"paper_order_created":False,"real_orders":False,"model_runtime_verified":False,"live_data_verified":False}
    if not market_enabled(m):d["status"]="disabled";return d
    s,sym=state(db,m);d["symbol"]=sym
    if not s:return d
    q=s["quote"];pos=s["position"];d["source"]=q["source"]
    d["scope"]={"policy":VERSION,"market":m,"symbol":sym,"source":q["source"],"venue":q.get("venue"),"fx_source":q.get("fx",{}).get("source"),"pool":s.get("pool")}
    d["quote_at"]=q["source_at"]
    if m=="SOLANA":fresh=sol.fresh(q,now);gate=sol.risk_ok(s) and sol.entry_gate(q,now)
    elif m=="FUTURES":
        fresh=fut.fresh(q,now) and not(pos and int(now.timestamp()//fut.FUNDING_PERIOD)>int(ts(q["source_at"]).timestamp()//fut.FUNDING_PERIOD))
        gate=fut.risk_ok(s) and fut.entry_gate(q)
    else:
        fresh=stocks.fresh(q,now,m);gate=not stocks.blocked(s) and "venue" in q and D(q.get("bid_size","0"))>=1 and D(q.get("ask_size","0"))>=1
    if not fresh:d["status"]="stale_or_funding_missing";return d
    d["research_context"]=context(m,sym,now)
    prices,n=completed_minutes(db,m,q,now);d["observations"]=n
    if not prices:d["status"]="insufficient_contiguous_minutes";return d
    regime=classify(prices);d["regime"]=regime
    # Independent diagnostic only. Keep the original strategy and gates unchanged.
    d["regime_diagnostic"]=diagnose(m,prices,q,now)
    d["signals"]={name:signal(name,prices,WINDOW) for name in CANDIDATES}
    # Fixed rule for diagnostic consensus only; no optimization or prediction claim.
    candidate="trend" if regime["id"]=="bull" and d["signals"]["trend"] and d["signals"]["momentum"] else "reversion" if regime["id"]=="sideways" and d["signals"]["reversion"] else "cash"
    d["candidate"]=candidate;d["status"]="shadow_evaluated"
    if any(candidate in row["quarantined"] for row in d["research_context"]):d["blockers"].append("research_context_quarantine");candidate="cash"
    if halted(db):gate=False;d["blockers"].append("kill_switch")
    if not gate:d["blockers"].append("risk_or_market_gate")
    if s["pending"] or pos:d["blockers"].append("position_or_pending")
    if candidate!="cash" and gate and not pos and not s["pending"]:d["hypothetical_action"]="LONG" if m=="FUTURES" else "BUY"
    elif m=="FUTURES" and regime["id"]=="bear" and not d["signals"]["trend"] and not d["signals"]["momentum"] and gate and not pos and not s["pending"] and not any("trend" in row["quarantined"] for row in d["research_context"]):d["hypothetical_action"]="SHORT";d["candidate"]="trend"
    return d
def record(m,*,clock=stocks.utc):
    if m not in MARKETS or not market_enabled(m):raise PilotError("Gölge karar izni kapalı.")
    p=stocks.path()
    if not p.is_file():raise PilotError("Gözlem kaydı yok.")
    with stocks.tx() as db:
        now=clock();d=evaluate(db,m,now)
        if d["status"] in ("disabled","no_observation"):return {**d,"recorded":False}
        # Once per completed-minute decision, across process restarts.
        latest=db.execute("SELECT payload FROM observed_events WHERE market=? AND event='shadow_decision' ORDER BY id DESC LIMIT 1",(m,)).fetchone()
        if latest:
            prior=json.loads(latest[0])
            if prior["minute"]>=d["minute"]:return {**prior,"recorded":False,"duplicate":True}
        d["id"]=hashlib.sha256(json.dumps([VERSION,m,d["symbol"],d.get("source"),d["minute"]],separators=(",",":")).encode()).hexdigest()
        db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES(?,?,?,?)",(m,now.isoformat(),"shadow_decision",json.dumps(d,ensure_ascii=False,allow_nan=False)))
        return {**d,"recorded":True}
def snapshot(*,clock=stocks.utc):
    now=clock();out={"enabled":enabled(),"mode":"shadow_only","markets":[{"market":m,"status":"disabled" if not market_enabled(m) else "no_decision","latest":None} for m in MARKETS],"automatic_entry_enabled":False,"real_orders":False}
    p=stocks.path()
    if not enabled() or not p.is_file():return out
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='observed_events'").fetchone():return out
        for row in out["markets"]:
            if not market_enabled(row["market"]):continue
            v=db.execute("SELECT payload FROM observed_events WHERE market=? AND event='shadow_decision' ORDER BY id DESC LIMIT 1",(row["market"],)).fetchone()
            if v:
                d=json.loads(v[0]);row.update(status="recorded" if 0<=(now-ts(d["as_of"])).total_seconds()<=60 else "historical",latest=d)
    return out
