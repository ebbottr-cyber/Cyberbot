"""Bounded non-overlapping forward quote diagnostics, never an order authorization."""
import json,sqlite3
from contextlib import closing
from decimal import Decimal as D
from datetime import timedelta
from . import observed_pilot as p,solana_pilot as sol,futures_pilot as fut,pilot_decisions as dec
from .pilot_control import halted
from .observed_pilot import ts,PilotError
VERSION="shadow-outcome-2"
HORIZON=300
WINDOW=360
MAX_ROWS=500
MIN_SAMPLE=30
def prices(m,q,direction,cost):
    slip,fee=(sol.SLIP,sol.FEE) if m=="SOLANA" else (fut.SLIP,fut.FEE) if m=="FUTURES" else (p.SLIP,p.FEE)
    if direction=="SHORT":
        return D(q["bid"])*(1-slip*cost)*(1-fee*cost),D(q["ask"])*(1+slip*cost)*(1+fee*cost)
    return D(q["ask"])*(1+slip*cost)*(1+fee*cost)*p.rate(q,"ask"),D(q["bid"])*(1-slip*cost)*(1-fee*cost)*p.rate(q,"bid")
def measurement(db,m,d,now):
    start=ts(d["as_of"]);end=start+timedelta(seconds=WINDOW)
    out={"version":VERSION,"decision_id":d["id"],"decision_at":d["as_of"],"covered_until":end.isoformat(),"market":m,"symbol":d["symbol"],"source":d.get("source"),"direction":d["hypothetical_action"],"scope":d.get("scope"),"candidate":d.get("candidate"),"regime":(d.get("regime") or {}).get("id"),"decision_version":d.get("version"),"status":"unmeasurable","reason":"missing_or_invalid_observations","net_pct":None,"double_cost_pct":None,"execution_verified":False}
    rows=db.execute("SELECT at,payload FROM observed_events WHERE market=? AND at>? AND at<=? AND event NOT IN ('shadow_decision','shadow_outcome','request') ORDER BY id LIMIT ?",(m,start.isoformat(),end.isoformat(),MAX_ROWS+1)).fetchall()
    if len(rows)>MAX_ROWS:return {**out,"reason":"scope_limit"}
    seq=[]
    for at,payload in rows:
        q=json.loads(payload).get("quote")
        if not q:continue
        t=ts(q["source_at"]);recorded=ts(at)
        if q["source"]!=d.get("source") or not start<t<=recorded<=min(now,end) or (recorded-t).total_seconds()>30:continue
        if seq and (t-seq[-1][0]).total_seconds()<=0:return out
        seq.append((t,q))
    if not seq or (seq[0][0]-start).total_seconds()>30:return out
    entry_t,a=seq[0];target=entry_t+timedelta(seconds=HORIZON);prev=entry_t;b=None
    for t,q in seq[1:]:
        if (t-prev).total_seconds()>30:return out
        prev=t
        if t>=target:b=q;break
    if b is None or (prev-target).total_seconds()>30 or entry_t.date()!=prev.date():return out
    if m=="FUTURES" and int(entry_t.timestamp()//fut.FUNDING_PERIOD)!=int(prev.timestamp()//fut.FUNDING_PERIOD):return {**out,"reason":"funding_boundary"}
    if m in p.ACCOUNTS:
        if not a.get("venue") or a.get("venue")!=b.get("venue") or D(a.get("ask_size","0"))<1 or D(b.get("bid_size","0"))<1:return {**out,"reason":"depth_or_venue"}
        if m=="XETRA" and any("fx" not in x or not 0<=(ts(x["source_at"])-ts(x["fx"]["source_at"])).total_seconds()+10<=20 for x in (a,b)):return {**out,"reason":"fx_missing"}
    else:
        unit="usdt" if m=="FUTURES" else "usd"
        side=d["hypothetical_action"]
        if min(D(a[("bid" if side=="SHORT" else "ask")+"_depth_"+unit]),D(b[("ask" if side=="SHORT" else "bid")+"_depth_"+unit]))<100:return {**out,"reason":"depth"}
        if m=="SOLANA" and not sol.entry_gate(a,entry_t):return {**out,"reason":"security_or_liquidity"}
    def edge(cost):
        e,_=prices(m,a,d["hypothetical_action"],cost);_,x=prices(m,b,d["hypothetical_action"],cost)
        result=(e-x)/e if d["hypothetical_action"]=="SHORT" else (x-e)/e
        if m=="SOLANA":result-=2*sol.FIXED*cost/D(25)
        return str((result*100).quantize(D(".000001")))
    return {**out,"status":"measured","reason":None,"entry_at":entry_t.isoformat(),"exit_at":prev.isoformat(),"net_pct":edge(1),"double_cost_pct":edge(2)}
def record(m,*,clock=p.utc):
    if m not in dec.MARKETS or not dec.market_enabled(m):raise PilotError("Gölge ölçüm izni kapalı.")
    if not p.path().is_file():return {"status":"no_observation"}
    with p.tx() as db:
        now=clock();prior=db.execute("SELECT payload FROM observed_events WHERE market=? AND event='shadow_outcome' ORDER BY id DESC LIMIT 1",(m,)).fetchone()
        last=json.loads(prior[0]) if prior else None
        after=last["covered_until"] if last else ""
        rows=db.execute("SELECT payload FROM observed_events WHERE market=? AND event='shadow_decision' AND json_extract(payload,'$.hypothetical_action') IN ('BUY','LONG','SHORT') AND at>=? AND at<=? ORDER BY id LIMIT 1",(m,after,(now-timedelta(seconds=WINDOW)).isoformat())).fetchall()
        for (payload,) in rows:
            d=json.loads(payload)
            if d.get("hypothetical_action") not in ("BUY","LONG","SHORT"):continue
            out=measurement(db,m,d,now)
            db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES(?,?,?,?)",(m,now.isoformat(),"shadow_outcome",json.dumps(out,allow_nan=False)))
            return out
        return {"status":"no_mature_candidate"}
def snapshot():
    result={"mode":"forward_quote_diagnostic","minimum_sample":MIN_SAMPLE,"automatic_entry_enabled":False,"real_orders":False,"markets":[],"limitations":["5 dakikalık yönsel kotasyon getirisi; sanal işlem veya strateji kârlılığı değildir.","Futures fonlama sınırı dışlanır, kaldıraç/likidasyon performansı ölçülmez. Solana 25 USD nominal maliyet varsayımı.","En son 100 ölçüm/piyasa; boşluk veya başarısız ölçüm olumlu kanıt değildir. Otomatik giriş için yeterlilik sağlamaz."]}
    path=p.path()
    if not dec.enabled() or not path.is_file():return result
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='observed_events'").fetchone():return result
        for m in dec.MARKETS:
            if not dec.market_enabled(m):continue
            recent=[json.loads(x[0]) for x in db.execute("SELECT payload FROM observed_events WHERE market=? AND event='shadow_outcome' ORDER BY id DESC LIMIT 100",(m,))]
            good=[x for x in recent if x["status"]=="measured"];n=len(good)
            mean=lambda k:str((sum(D(x[k]) for x in good)/n).quantize(D(".000001"))) if n else None
            result["markets"].append({"market":m,"attempts":len(recent),"measured":n,"mean_net_pct":mean("net_pct"),"mean_double_cost_pct":mean("double_cost_pct"),"sample_threshold_met":n>=MIN_SAMPLE,"authorization":"blocked_unverified_source_and_execution","entry_halted":halted(db),"latest":recent[0] if recent else None})
    return result
