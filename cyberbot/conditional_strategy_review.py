"""Read-only conditional review of previously logged shadow candidates.

Only the chosen historical action was observed. This is not a counterfactual
strategy tournament or authorization to trade.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal as D
import json
from statistics import mean

from .observed_pilot import ts
from .observed_regime import VERSION as REGIME_VERSION
from . import pilot_decisions as decisions

VERSION="conditional-strategy-review-1"
MIN_MEASURED=30
MIN_DAYS=10
MIN_COVERAGE=D("0.8")
MAX_OUTCOMES=500
WINDOW=360
MAX_AGE_DAYS=30


def group_key(d):
    scope=d["scope"]
    if (d["version"]!="pilot-shadow-2" or d["mode"]!="shadow_only"
            or d["actual_action"]!="HOLD" or d["paper_order_created"] is not False
            or d["real_orders"] is not False
            or scope["policy"]!=d["version"]
            or any(scope[k]!=d[k] for k in ("market","symbol","source"))):
        raise ValueError("invalid shadow scope")
    r=d["regime_diagnostic"]
    if (r["version"]!=REGIME_VERSION or r["market"]!=d["market"]
            or r["interval"]!="1m" or r["observations"]!=21
            or r["real_orders"] is not False or r["execution_verified"] is not False):
        raise ValueError("invalid diagnostic scope")
    direction,vol,book=r["direction"],r["volatility"],r["liquidity"]["status"]
    if direction not in ("bull","bear","sideways") or vol not in ("normal","high") or book not in ("unknown","constrained","asserted_threshold_met"):
        raise ValueError("invalid regime")
    return (json.dumps(scope,sort_keys=True,separators=(",",":")),direction,vol,book)


def matched(d,o,recorded,now):
    key=group_key(d)
    if (o["version"]!="shadow-outcome-2" or o["decision_id"]!=d["id"]
            or o["decision_at"]!=d["as_of"] or o["decision_version"]!=d["version"]
            or o["scope"]!=d["scope"] or o["execution_verified"] is not False
            or any(o[k]!=d[k] for k in ("market","symbol","source","candidate"))
            or o["direction"]!=d["hypothetical_action"]):
        raise ValueError("outcome mismatch")
    strategy,action=d["candidate"],d["hypothetical_action"]
    if strategy not in decisions.CANDIDATES or action not in (("LONG","SHORT") if d["market"]=="FUTURES" else ("BUY",)):
        raise ValueError("invalid action")
    start,end,at=ts(d["as_of"]),ts(o["covered_until"]),ts(recorded)
    if not now-timedelta(days=MAX_AGE_DAYS)<=start<end<=at<=now or end-start!=timedelta(seconds=WINDOW):
        raise ValueError("invalid outcome timing")
    if o["status"]=="unmeasurable":
        return key,(strategy,action),start,end,None
    if o["status"]!="measured":
        raise ValueError("invalid outcome status")
    entry,exit=ts(o["entry_at"]),ts(o["exit_at"])
    if not start<entry<=start+timedelta(seconds=30) or not entry+timedelta(seconds=300)<=exit<=min(end,entry+timedelta(seconds=330)):
        raise ValueError("invalid measurement window")
    values=tuple(D(str(o[k])) for k in ("net_pct","double_cost_pct"))
    if any(not v.is_finite() or abs(v)>10000 for v in values):
        raise ValueError("invalid return")
    return key,(strategy,action),start,end,values


def review(current, rows, now):
    result={"version":VERSION,"status":"INSUFFICIENT_EVIDENCE","action":"HOLD",
            "candidate":None,"groups":[],"automatic_strategy_switching":False,
            "real_orders":False,"execution_verified":False,
            "counterfactual_comparison":False,"profitability_verified":False}
    try:
        key=group_key(current)
        if not 0<=(now-ts(current["as_of"])).total_seconds()<=60:
            return {**result,"status":"STALE_DECISION"}
    except (ValueError,KeyError,TypeError,ArithmeticError):
        return {**result,"status":"NO_COMPATIBLE_DIAGNOSTIC"}
    if key[2]!="normal" or key[3]!="asserted_threshold_met":
        return {**result,"status":"RISK_CONTEXT_HOLD"}
    if any(b not in ("no_compatible_observed_minute_forward_evidence","automatic_entry_disabled") for b in current.get("blockers",[])):
        return {**result,"status":"EXISTING_GATE_HOLD"}
    buckets=defaultdict(list)
    seen=set()
    last_end=None
    rejected=0
    for d,o,at in rows:
        try:
            item=matched(d,o,at,now)
            k,pair,start,end,values=item
            if d["id"] in seen or (last_end is not None and start<last_end):
                raise ValueError("duplicate or overlapping outcome")
        except (ValueError,KeyError,TypeError,ArithmeticError):
            rejected+=1
            continue
        seen.add(d["id"])
        last_end=end
        if k==key:
            buckets[pair].append((start.date(),values))
    result["rejected"]=rejected
    for (strategy,action),items in sorted(buckets.items()):
        good=[(day,v) for day,v in items if v is not None]
        days=sorted({day for day,v in good})
        coverage=D(len(good))/len(items)
        row={"strategy":strategy,"direction":action,"attempts":len(items),
             "measured":len(good),"days":len(days),"coverage":str(coverage),
             "eligible_for_review":False}
        if len(good)>=MIN_MEASURED and len(days)>=MIN_DAYS and coverage>=MIN_COVERAGE:
            # Separate whole UTC days; equal day weights, both costs positive.
            holdout=set(days[len(days)*2//3:])
            a=[v for day,v in good if day not in holdout]
            b=[v for day,v in good if day in holdout]
            def score(wanted):
                return [mean(mean(v[i] for day,v in good if day==d) for d in wanted) for i in (0,1)]
            if len(a)>=20 and len(b)>=10:
                dev,test=score(set(days)-holdout),score(holdout)
                row.update(development_net_pct=str(dev[0]),development_stress_pct=str(dev[1]),
                           holdout_net_pct=str(test[0]),holdout_stress_pct=str(test[1]),
                           eligible_for_review=all(v>0 for v in dev+test))
        result["groups"].append(row)
    if rejected:
        return {**result,"status":"DATA_REVIEW_REQUIRED"}
    eligible=[r for r in result["groups"] if r["eligible_for_review"]]
    # Only the existing currently signalled pair may be reviewed; never invent
    # an alternative from selectively observed historical actions.
    pair=(current["candidate"],current["hypothetical_action"])
    found=next((r for r in eligible if (r["strategy"],r["direction"])==pair),None)
    if found:
        result.update(status="REVIEW_ONLY",candidate=found["strategy"],candidate_direction=found["direction"])
    return result


def snapshot(db,market,now):
    """Caller supplies read-only pilot DB. Bound scan, use exact decision ID."""
    row=db.execute("SELECT payload FROM observed_events WHERE market=? AND event='shadow_decision' ORDER BY id DESC LIMIT 1",(market,)).fetchone()
    if not row:
        return {"version":VERSION,"status":"NO_DECISION","action":"HOLD","real_orders":False}
    current=json.loads(row[0])
    raw=db.execute("""SELECT at,payload FROM observed_events WHERE market=? AND event='shadow_outcome'
        AND at>=? ORDER BY id DESC LIMIT ?""",(market,(now-timedelta(days=MAX_AGE_DAYS)).isoformat(),MAX_OUTCOMES)).fetchall()
    rows=[]
    for at,payload in reversed(raw):
        o=json.loads(payload)
        matches=db.execute("""SELECT payload FROM observed_events WHERE market=? AND event='shadow_decision'
            AND at=? AND json_extract(payload,'$.id')=? LIMIT 2""",(market,o.get("decision_at"),o.get("decision_id"))).fetchall()
        if len(matches)!=1:
            rows.append(({},o,at))
            continue
        d=json.loads(matches[0][0])
        # Legacy rows have no compatible diagnostic; not negative evidence.
        if not d.get("regime_diagnostic"):
            continue
        rows.append((d,o,at))
    return review(current,rows,now)
