"""Offline quote-only paper replay; no fills, positions, strategy or execution authorization."""
import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from cyberbot.solana_pilot import address
from cyberbot.providers.solana_observed import USDC, uint
from tools.solana_route_preview import accounting
from tools.dexterm_research_archive import APP_ID, MAX_BYTES, FLAGS

SCALE=1_000_000
FALSE_FLAGS={k:False for k in FLAGS}
FALSE_FLAGS.update(route_integrity_verified=False,depth_verified=False,
                   profitability_verified=False,execution_verified=False,
                   strategy_evaluated=False,real_fills=False)

def instant(value):
    if not isinstance(value,str) or len(value)>64:raise ValueError("Invalid timestamp")
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None:raise ValueError("Timezone required")
    return dt.astimezone(timezone.utc)

def no_clearance(row,flags=FLAGS):
    if not isinstance(row,dict) or any(row.get(k) is not False for k in flags):
        raise ValueError("Unexpected verification flags")

def leg_amounts(route,inp,out):
    if not isinstance(route,dict) or route.get("route_integrity_verified") is not False:
        raise ValueError("Invalid route flags")
    amount=uint(route["reported_input_raw"],True)
    received=uint(route["reported_output_raw"],True)
    legs=route["legs"]
    if not isinstance(legs,list) or not 1<=len(legs)<=32:raise ValueError("Invalid leg count")
    for leg in legs:
        if not all(address(leg.get(k)) for k in ("pool","input_mint","output_mint")) or leg["input_mint"]==leg["output_mint"]:
            raise ValueError("Invalid leg identity")
        uint(leg["input_raw"],True);uint(leg["output_raw"],True)
        if type(leg.get("bps")) is not int or not 1<=leg["bps"]<=10000:
            raise ValueError("Invalid allocation")
    computed=accounting(legs,inp,out,amount,received)
    if computed!=route.get("accounting") or not computed["reported_input_and_intermediate_balanced"] or computed["source_bps_sum"]!=10000:
        raise ValueError("Unbalanced reported route")
    delta=int(computed["terminal_gross_minus_reported_raw"])
    if delta<0:raise ValueError("Reported output exceeds gross route output")
    return amount,received,delta

def observation(item):
    c=item["candidate"];d=item["diagnostic"]
    no_clearance(d)
    if d.get("status")!="diagnostic_complete":raise ValueError("Incomplete diagnostic")
    mint=c["mint"];pool=c["pool"]
    if not address(mint) or not address(pool) or mint==USDC or d.get("mint")!=mint or d.get("reference_pool")!=pool:
        raise ValueError("Snapshot identity mismatch")
    stages=d["stages"]
    if any(stages.get(k,{}).get("status")!="ok" for k in ("mint","holders","reference_pool","route_preview")):
        raise ValueError("Incomplete stages")
    mint_info=stages["mint"]["data"]
    if mint_info.get("mint_authority_disabled") is not True or mint_info.get("freeze_authority_disabled") is not True:
        raise ValueError("Authority policy exclusion")
    q=stages["route_preview"]["data"]
    no_clearance(q,(*FLAGS,"route_integrity_verified","depth_verified","quote_source_timestamp_verified","transport_mocked"))
    if q.get("status")!="route_preview_only" or q.get("mint")!=mint:
        raise ValueError("Invalid preview")
    stamp=instant(q["retrieved_at"])
    if not 0<=(instant(d["retrieved_at"])-stamp).total_seconds()<=60:
        raise ValueError("Snapshot timestamp mismatch")
    amount,tokens,buy_delta=leg_amounts(q["buy"],USDC,mint)
    sell_input,received,sell_delta=leg_amounts(q["sell"],mint,USDC)
    if tokens!=sell_input or not SCALE<=amount<=100*SCALE:
        raise ValueError("Roundtrip amount mismatch")
    if Decimal(q["test_input_usdc"])!=Decimal(amount)/SCALE or Decimal(q["reported_roundtrip_return_usdc"])!=Decimal(received)/SCALE:
        raise ValueError("Roundtrip summary mismatch")
    return {"mint":mint,"pool":pool,"timestamp":stamp.isoformat(),"input_raw":amount,
            "token_amount_raw":tokens,"return_raw":received,"buy_terminal_delta_raw":str(buy_delta),
            "sell_terminal_delta_raw":str(sell_delta),"fee_semantics_verified":False}

def window_filter(window):
    if window is None:return "",(),None
    if not isinstance(window,(tuple,list)) or len(window)!=2:raise ValueError("Both import window endpoints required")
    start,end=map(instant,window)
    if not 0<(end-start).total_seconds()<=30*86400:raise ValueError("Import window must be at most 30 days")
    values=(start.isoformat(),end.isoformat())
    return " AND imported_utc>=? AND imported_utc<?",values,{"basis":"archive_import_utc","start_inclusive":values[0],"end_exclusive":values[1]}

def collect(database,limit,*,window=None):
    if type(limit) is not int or not 1<=limit<=500:raise ValueError("Bridge limit 1 to 500")
    clause,params,selection=window_filter(window)
    path=Path(database).resolve(strict=True)
    con=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=10)
    observations=[];excluded=0;incomplete=0;duplicates=0;seen=set();read=0;truncated=False
    try:
        if con.execute("PRAGMA application_id").fetchone()[0]!=APP_ID or con.execute("PRAGMA user_version").fetchone()[0]!=1:
            raise ValueError("Wrong research database")
        # Stream bounded reports instead of loading up to 500 multi-MiB
        # payloads at once. The extra row detects truncation.
        cursor=con.execute("SELECT digest,CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END FROM research_reports WHERE kind='bridge'"+clause+" ORDER BY imported_utc DESC,digest DESC LIMIT ?",(MAX_BYTES,*params,limit+1))
        for digest,body in cursor:
            if read==limit:
                truncated=True;break
            read+=1
            if not isinstance(body,str) or len(body.encode("utf-8"))>MAX_BYTES:
                raise ValueError("Oversized or invalid archived report")
            if hashlib.sha256(body.encode("utf-8")).hexdigest()!=digest:
                raise ValueError("Archived report digest mismatch")
            report=json.loads(body)
            no_clearance(report)
            if report.get("source")!="dexterm_historical_shortlist_exact_mint_lookup":
                raise ValueError("Invalid bridge source")
            scan=report.get("scan")
            if scan is None:continue
            no_clearance(scan)
            items=scan["reports"]
            if not isinstance(items,list) or len(items)>3:raise ValueError("Invalid archived report count")
            for i,item in enumerate(items):
                if item["diagnostic"].get("status")!="diagnostic_complete":
                    incomplete+=1;continue
                try:o=observation(item)
                except (ValueError,KeyError,TypeError,ArithmeticError,AttributeError):
                    excluded+=1;continue
                key=(o["mint"],o["timestamp"],o["input_raw"],o["token_amount_raw"],o["return_raw"])
                if key in seen:duplicates+=1;continue
                seen.add(key)
                observations.append(dict(o,source_digest=digest,source_index=i))
    finally:con.close()
    observations.sort(key=lambda o:(instant(o["timestamp"]),o["mint"],o["source_digest"],o["source_index"]))
    return observations,{"bridge_reports_read":read,"bridge_history_truncated":truncated,
                         "incomplete_diagnostics":incomplete,"excluded_diagnostics":excluded,"duplicate_quotes":duplicates,"archive_import_window":selection}

def fee(amount,bps):
    return (amount*bps+9999)//10000

def replay(database,*,initial_usdc=1000,stress_bps=25,limit=100):
    if type(initial_usdc) is not int or not 100<=initial_usdc<=1000000:raise ValueError("Invalid paper capital")
    if type(stress_bps) is not int or not 0<=stress_bps<=1000:raise ValueError("Invalid stress basis points")
    rows,stats=collect(database,limit)
    starting=initial_usdc*SCALE
    cash=starting;peak=cash;drawdown=0;baseline_net=0;stress_total=0;wins=0;skipped=0;events=[]
    for row in rows:
        n=row["input_raw"];returned=row["return_raw"]
        entry_stress=fee(n,stress_bps);exit_stress=fee(returned,stress_bps)
        if cash<n+entry_stress:
            skipped+=1;continue
        delta=returned-n-entry_stress-exit_stress
        cash+=delta;peak=max(cash,peak);drawdown=max(drawdown,peak-cash)
        baseline_net+=returned-n;stress_total+=entry_stress+exit_stress;wins+=delta>0
        events.append(dict(row,reported_net_raw=returned-n,extra_cost_raw=entry_stress+exit_stress,
                           stressed_net_raw=delta,simulated_balance_raw=cash))
    return {"status":"quote_replay_complete" if events else "no_usable_quotes",
            "research_only":True,"paper_replay_only":True,"network_requests":False,
            "capital_assumption_usdc":initial_usdc,"extra_cost_bps_per_leg":stress_bps,
            "initial_balance_raw":starting,"final_balance_raw":cash,
            "reported_net_raw":baseline_net,"extra_cost_total_raw":stress_total,
            "stressed_net_raw":cash-starting,"max_balance_drawdown_raw":drawdown,
            "scenarios_replayed":len(events),"positive_scenarios":wins,"insufficient_capital_scenarios":skipped,
            "terminal_delta_scenarios":sum(e["buy_terminal_delta_raw"]!="0" or e["sell_terminal_delta_raw"]!="0" for e in events),
            "fee_semantics_verified":False,"quote_source_timestamp_verified":False,
            "events":events,**stats,**FALSE_FLAGS}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--initial-usdc",type=int,default=1000)
    p.add_argument("--stress-bps",type=int,default=25)
    p.add_argument("--limit",type=int,default=100)
    a=p.parse_args()
    try:
        out=replay(a.database,initial_usdc=a.initial_usdc,stress_bps=a.stress_bps,limit=a.limit)
        print(json.dumps(out,indent=2,allow_nan=False))
        return 0 if out["status"]=="quote_replay_complete" else 2
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
