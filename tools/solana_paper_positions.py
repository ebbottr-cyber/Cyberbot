"""Offline fixed-horizon paper positions; only exact-quantity observed exit quotes."""
import argparse
import json
import sqlite3
from itertools import groupby
from tools.solana_paper_replay import collect,instant,fee,SCALE,FALSE_FLAGS

def simulate(rows,*,initial_usdc=1000,stress_bps=25,hold_seconds=180,max_positions=3):
    for value,low,high in ((initial_usdc,100,1000000),(stress_bps,0,1000),
                           (hold_seconds,60,86400),(max_positions,1,10)):
        if type(value) is not int or not low<=value<=high:
            raise ValueError("Invalid simulation configuration")
    starting=initial_usdc*SCALE
    cash=starting
    positions={};events=[];closed=[];skips={};last_time=None
    def skip(reason):
        skips[reason]=skips.get(reason,0)+1
    ordered=sorted(rows,key=lambda r:(instant(r["timestamp"]),r["mint"],r["source_digest"],r["source_index"]))
    # Each timestamp is a batch. Conflicting observations of a mint are not
    # used to pick whichever price happens to look best.
    for now,batch in groupby(ordered,key=lambda r:instant(r["timestamp"])):
        last_time=now
        grouped={}
        for r in batch:grouped.setdefault(r["mint"],[]).append(r)
        usable={}
        for mint,items in grouped.items():
            if len(items)!=1:
                skip("ambiguous_same_time_observation");continue
            usable[mint]=items[0]
        previously_open=set(positions)
        # Close first; no same-batch re-entry for a mint already held.
        for mint,r in sorted(usable.items()):
            if mint not in positions:continue
            pos=positions[mint]
            elapsed=(now-instant(pos["opened_at"])).total_seconds()
            if elapsed<hold_seconds:continue
            if r["token_amount_raw"]!=pos["quantity_raw"]:
                skip("exit_quantity_mismatch");continue
            proceeds=r["return_raw"]
            cost=fee(proceeds,stress_bps)
            pnl=proceeds-cost-pos["entry_total_raw"]
            cash+=proceeds-cost
            trade=dict(pos,closed_at=now.isoformat(),holding_seconds=elapsed,
                       exit_source_digest=r["source_digest"],exit_source_index=r["source_index"],
                       exit_reported_raw=proceeds,exit_extra_cost_raw=cost,realized_net_raw=pnl)
            closed.append(trade)
            events.append({"kind":"paper_close","mint":mint,"timestamp":now.isoformat(),
                           "realized_net_raw":pnl,"cash_raw":cash})
            del positions[mint]
        for mint,r in sorted(usable.items()):
            if mint in previously_open:continue
            n=r["input_raw"];cost=fee(n,stress_bps)
            if len(positions)>=max_positions:
                skip("position_limit");continue
            if cash<n+cost:
                skip("insufficient_cash");continue
            # No entry test uses the simultaneous sell quote or future prices.
            pos={"mint":mint,"opened_at":now.isoformat(),"quantity_raw":r["token_amount_raw"],
                 "entry_input_raw":n,"entry_extra_cost_raw":cost,"entry_total_raw":n+cost,
                 "entry_source_digest":r["source_digest"],"entry_source_index":r["source_index"]}
            cash-=n+cost
            positions[mint]=pos
            events.append({"kind":"paper_open","mint":mint,"timestamp":now.isoformat(),
                           "quantity_raw":pos["quantity_raw"],"cash_raw":cash})
    open_rows=[]
    for mint,pos in sorted(positions.items()):
        elapsed=(last_time-instant(pos["opened_at"])).total_seconds()
        open_rows.append(dict(pos,age_at_end_seconds=elapsed,
                              exit_status="exit_quote_missing_or_quantity_mismatch" if elapsed>=hold_seconds else "holding_period_not_elapsed",
                              market_value_raw=None))
    realized=sum(p["realized_net_raw"] for p in closed)
    committed=sum(p["entry_total_raw"] for p in open_rows)
    if cash+committed!=starting+realized:
        raise ValueError("Paper cash accounting invariant failed")
    return {"status":"position_replay_complete" if events else "no_position_observations",
            "research_only":True,"paper_position_replay_only":True,"network_requests":False,
            "entry_policy":"first_observation_when_flat_and_cash_available",
            "exit_policy":"first_later_exact_quantity_quote_after_minimum_hold",
            "minimum_hold_seconds":hold_seconds,"max_open_positions":max_positions,
            "extra_cost_bps_per_direction":stress_bps,"initial_balance_raw":starting,
            "available_cash_raw":cash,"open_cost_basis_raw":committed,"realized_net_raw":realized,
            "final_equity_raw":None if open_rows else cash,
            "unrealized_net_raw":None if open_rows else 0,
            "closed_positions":len(closed),"open_positions":len(open_rows),
            "positive_closed_positions":sum(p["realized_net_raw"]>0 for p in closed),
            "skips":skips,"closed":closed,"open":open_rows,"events":events,
            "quote_source_timestamp_verified":False,"fee_semantics_verified":False,
            "portfolio_mark_to_market_verified":False,**FALSE_FLAGS}

def replay(database,*,initial_usdc=1000,stress_bps=25,hold_seconds=180,max_positions=3,limit=100):
    rows,stats=collect(database,limit)
    return dict(simulate(rows,initial_usdc=initial_usdc,stress_bps=stress_bps,
                         hold_seconds=hold_seconds,max_positions=max_positions),**stats)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--initial-usdc",type=int,default=1000)
    p.add_argument("--stress-bps",type=int,default=25)
    p.add_argument("--hold-seconds",type=int,default=180)
    p.add_argument("--max-positions",type=int,default=3)
    p.add_argument("--limit",type=int,default=100)
    a=p.parse_args()
    try:
        d=replay(a.database,initial_usdc=a.initial_usdc,stress_bps=a.stress_bps,
                 hold_seconds=a.hold_seconds,max_positions=a.max_positions,limit=a.limit)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"]=="position_replay_complete" else 2
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
