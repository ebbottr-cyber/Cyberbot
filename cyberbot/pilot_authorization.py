"""Fail-closed automatic-entry audit, no execution authority or provider calls."""
import os,json,sqlite3
from contextlib import closing
from datetime import timedelta
from decimal import Decimal as D
from . import observed_pilot as p,pilot_decisions as dec,pilot_outcomes as outcomes
from .pilot_control import halted
from .observed_pilot import ts
VERSION="paper-entry-audit-1"
MIN_SAMPLE=30
MIN_DAYS=3
MAX_HISTORY=1000
MAX_AGE_DAYS=30
def evidence(db,m,d,now):
    result={"attempts":0,"measured":0,"days":0,"mean_net_pct":None,"mean_double_cost_pct":None,"positive_double_cost_pct":None,"threshold_met":False,"scope_limit":False}
    if not d.get("scope") or d.get("hypothetical_action") not in ("BUY","LONG","SHORT"):return result
    rows=db.execute("SELECT at,payload FROM observed_events WHERE market=? AND event='shadow_outcome' AND at>=? AND at<=? ORDER BY id DESC LIMIT ?",(m,(now-timedelta(days=MAX_AGE_DAYS)).isoformat(),now.isoformat(),MAX_HISTORY+1)).fetchall()
    if len(rows)>MAX_HISTORY:result["scope_limit"]=True;return result
    values=[];ids=set();intervals=[];days=set()
    for at,raw in reversed(rows):
        x=json.loads(raw)
        if (x.get("version"),x.get("decision_version"),x.get("scope"),x.get("candidate"),x.get("direction"),x.get("regime"))!=(outcomes.VERSION,dec.VERSION,d["scope"],d["candidate"],d["hypothetical_action"],d["regime"]["id"]):continue
        start,end=ts(x["decision_at"]),ts(x["covered_until"])
        if x["decision_id"] in ids or (intervals and start<intervals[-1][1]) or end-start!=timedelta(seconds=outcomes.WINDOW) or not now-timedelta(days=MAX_AGE_DAYS)<=start<end<=ts(at)<=now:
            result["invalid_history"]=True;return result
        ids.add(x["decision_id"]);intervals.append((start,end));result["attempts"]+=1
        if x["status"]!="measured":continue
        # Only accept a persisted decision with identical identity and scope.
        matches=db.execute("SELECT payload FROM observed_events WHERE market=? AND event='shadow_decision' AND at=? AND json_extract(payload,'$.id')=? LIMIT 2",(m,x["decision_at"],x["decision_id"])).fetchall()
        if len(matches)!=1:result["invalid_history"]=True;return result
        prior=json.loads(matches[0][0])
        if (prior.get("scope"),prior.get("candidate"),prior.get("hypothetical_action"),(prior.get("regime") or {}).get("id"),prior.get("version"))!=(d["scope"],d["candidate"],d["hypothetical_action"],d["regime"]["id"],dec.VERSION):
            result["invalid_history"]=True;return result
        a,b=D(x["net_pct"]),D(x["double_cost_pct"])
        if not a.is_finite() or not b.is_finite() or b>a:result["invalid_history"]=True;return result
        values.append((a,b));days.add(start.date())
    n=len(values)
    result.update(measured=n,days=len(days))
    if n:
        a=sum(v[0] for v in values)/n;b=sum(v[1] for v in values)/n;positive=D(sum(v[1]>0 for v in values))*100/n
        result.update(mean_net_pct=str(a.quantize(D(".000001"))),mean_double_cost_pct=str(b.quantize(D(".000001"))),positive_double_cost_pct=str(positive.quantize(D(".01"))),threshold_met=n>=MIN_SAMPLE and len(days)>=MIN_DAYS and n*10>=result["attempts"]*9 and a>0 and b>0 and positive>=50)
    return result
def snapshot(*,clock=p.utc):
    now=clock();path=p.path();out={"version":VERSION,"as_of":now.isoformat(),"automatic_entry_enabled":False,"real_orders":False,"authorization":"blocked","markets":[],"limitations":["Eşikler deneysel tanılama kurallarıdır, kârlılık kanıtı değildir.","Aynı strateji sürümü, sembol, kaynak, işlem yeri, kur kaynağı, havuz, rejim ve yön; son 30 gün içinde 30 ölçüm ve en az 3 UTC gün; %90 ölçülebilirlik, pozitif normal/çift maliyet ortalaması, en az %50 pozitif çift maliyet ölçümü.","Kaynak doğrulaması ve aynı motorla ileri sanal işlem performansı henüz yok. Hiçbir bayrak bu denetimden otomatik emir yetkisi üretmez."]}
    db=None
    try:
        if path.is_file():
            db=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=3)
            db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
            tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"observed_accounts","observed_events"}.issubset(tables):raise p.PilotError("Pilot şeması eksik.")
        for m in dec.MARKETS:
            item={"market":m,"authorization":"blocked","checks":{"pilot_permissions":dec.market_enabled(m),"kill_switch_clear":not (halted(db) if db else os.getenv("CYBERBOT_PILOT_KILL_SWITCH")=="1"),"current_signal":False,"scoped_forward_diagnostics":False,"provider_runtime_verified":False,"same_engine_forward_execution_verified":False,"operator_automatic_entry_grant":False},"evidence":None,"candidate":None,"direction":"HOLD","blockers":[]}
            if db and item["checks"]["pilot_permissions"]:
                try:
                    d=dec.evaluate(db,m,now)
                    item.update(candidate=d["candidate"],direction=d["hypothetical_action"])
                    item["checks"]["current_signal"]=d["status"]=="shadow_evaluated" and d["hypothetical_action"] in ("BUY","LONG","SHORT")
                    if item["checks"]["current_signal"]:
                        item["evidence"]=evidence(db,m,d,now)
                        item["checks"]["scoped_forward_diagnostics"]=item["evidence"]["threshold_met"]
                except (ValueError,KeyError,TypeError,ArithmeticError,sqlite3.Error):item["checks"]["current_signal"]=False;item["review_required"]=True
            item["blockers"]=[k for k,v in item["checks"].items() if not v]
            out["markets"].append(item)
        return out
    finally:
        if db is not None:db.close()
