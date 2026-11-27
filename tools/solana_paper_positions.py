"""Offline paper positions with optional risk policy; only exact-quantity observed exit quotes."""
import argparse
import json
import sqlite3
from itertools import groupby
from tools.solana_paper_replay import collect,instant,fee,SCALE,FALSE_FLAGS
from tools.solana_exit_history import bound,collect_exits

def simulate(rows,*,initial_usdc=1000,stress_bps=25,hold_seconds=180,max_positions=3,
             risk_mode=False,stop_loss_bps=300,take_profit_bps=500,
             exposure_bps=3500,position_bps=1500,loss_budget_bps=500,exit_quotes=()):
    for value,low,high in ((initial_usdc,100,1000000),(stress_bps,0,1000),
                           (hold_seconds,60,86400),(max_positions,1,10)):
        if type(value) is not int or not low<=value<=high:
            raise ValueError("Invalid simulation configuration")
    if type(risk_mode) is not bool:
        raise ValueError("Invalid risk mode")
    for value,low,high in ((stop_loss_bps,1,10000),(take_profit_bps,1,100000),
                           (exposure_bps,1,10000),(position_bps,1,10000),(loss_budget_bps,1,10000)):
        if type(value) is not int or not low<=value<=high:
            raise ValueError("Invalid risk configuration")
    if position_bps>exposure_bps:raise ValueError("Position cap exceeds exposure cap")
    starting=initial_usdc*SCALE
    exposure_cap=starting*exposure_bps//10000
    position_cap=starting*position_bps//10000
    loss_budget=starting*loss_budget_bps//10000
    gross_realized_loss=0
    entry_halted=False
    cash=starting
    positions={};events=[];closed=[];skips={};last_time=None
    def skip(reason):
        skips[reason]=skips.get(reason,0)+1
    exits=bound(rows,exit_quotes)
    ordered=sorted(list(rows)+exits,key=lambda r:(instant(r["timestamp"]),r["mint"],r["source_digest"],r["source_index"]))
    # Each timestamp is a batch. Conflicting observations of a mint are not
    # used to pick whichever price happens to look best.
    for now,batch in groupby(ordered,key=lambda r:instant(r["timestamp"])):
        last_time=now
        grouped={};explicit={}
        for r in batch:
            (explicit if r.get("exit_only") is True else grouped).setdefault(r["mint"],[]).append(r)
        usable={}
        for mint,items in grouped.items():
            if len(items)!=1:
                skip("ambiguous_same_time_observation");continue
            usable[mint]=items[0]
        previously_open=set(positions)
        # Close first; no same-batch re-entry for a mint already held.
        for mint in sorted(set(usable)|set(explicit)):
            if mint not in positions:continue
            pos=positions[mint]
            elapsed=(now-instant(pos["opened_at"])).total_seconds()
            if not risk_mode and elapsed<hold_seconds:continue
            candidates=[r for r in explicit.get(mint,[]) if
                        (r["entry_source_digest"],r["entry_source_index"])==(pos["entry_source_digest"],pos["entry_source_index"])]
            if mint in usable and usable[mint]["token_amount_raw"]==pos["quantity_raw"]:
                candidates.append(usable[mint])
            if not candidates:
                if mint in usable:skip("exit_quantity_mismatch")
                continue
            if len({r["return_raw"] for r in candidates})!=1:
                skip("ambiguous_same_time_exit");continue
            r=sorted(candidates,key=lambda r:(not r.get("exit_only",False),r["source_digest"],r["source_index"]))[0]
            proceeds=r["return_raw"]
            cost=fee(proceeds,stress_bps)
            pnl=proceeds-cost-pos["entry_total_raw"]
            exit_reason="time_exit"
            if risk_mode:
                basis=pos["entry_total_raw"]
                if pnl*10000<=-basis*stop_loss_bps:
                    exit_reason="stop_loss_observed"
                elif pnl*10000>=basis*take_profit_bps:
                    exit_reason="take_profit_observed"
                elif elapsed<hold_seconds:
                    continue
            cash+=proceeds-cost
            gross_realized_loss+=max(0,-pnl)
            if risk_mode and gross_realized_loss>=loss_budget:
                entry_halted=True
            trade=dict(pos,closed_at=now.isoformat(),holding_seconds=elapsed,
                       exit_source_digest=r["source_digest"],exit_source_index=r["source_index"],
                       exit_reported_raw=proceeds,exit_extra_cost_raw=cost,realized_net_raw=pnl,exit_reason=exit_reason)
            closed.append(trade)
            events.append({"kind":"paper_close","mint":mint,"timestamp":now.isoformat(),
                           "realized_net_raw":pnl,"cash_raw":cash,"exit_reason":exit_reason})
            del positions[mint]
        for mint,r in sorted(usable.items()):
            if mint in previously_open:continue
            n=r["input_raw"];cost=fee(n,stress_bps)
            if risk_mode:
                if entry_halted:
                    skip("realized_loss_budget_reached");continue
                if n+cost>position_cap:
                    skip("position_cost_cap");continue
                if sum(p["entry_total_raw"] for p in positions.values())+n+cost>exposure_cap:
                    skip("portfolio_cost_cap");continue
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
                              exit_status="exit_quote_missing_or_quantity_mismatch" if elapsed>=hold_seconds else "risk_threshold_unresolved_or_time_exit_not_due" if risk_mode else "holding_period_not_elapsed",
                              market_value_raw=None))
    realized=sum(p["realized_net_raw"] for p in closed)
    committed=sum(p["entry_total_raw"] for p in open_rows)
    if cash+committed!=starting+realized:
        raise ValueError("Paper cash accounting invariant failed")
    return {"status":"position_replay_complete" if events else "no_position_observations",
            "research_only":True,"paper_position_replay_only":True,"network_requests":False,
            "entry_policy":"first_observation_when_flat_and_cash_available",
            "exit_policy":"observed_stop_take_profit_or_time_exit" if risk_mode else "first_later_exact_quantity_quote_after_minimum_hold",
            "minimum_hold_seconds":None if risk_mode else hold_seconds,
            "time_exit_after_seconds":hold_seconds,"max_open_positions":max_positions,
            "risk_mode":risk_mode,"risk_policy":({"stop_loss_bps":stop_loss_bps,"take_profit_bps":take_profit_bps,
                        "cost_exposure_cap_raw":exposure_cap,"position_cost_cap_raw":position_cap,
                        "gross_realized_loss_budget_raw":loss_budget} if risk_mode else None),
            "gross_realized_loss_raw":gross_realized_loss,"entry_halted":entry_halted,
            "exit_reason_counts":{reason:sum(p["exit_reason"]==reason for p in closed)
                                  for reason in ("stop_loss_observed","take_profit_observed","time_exit")},
            "intraperiod_risk_verified":False,"loss_budget_is_guaranteed":False,
            "extra_cost_bps_per_direction":stress_bps,"initial_balance_raw":starting,
            "available_cash_raw":cash,"open_cost_basis_raw":committed,"realized_net_raw":realized,
            "final_equity_raw":None if open_rows else cash,
            "unrealized_net_raw":None if open_rows else 0,
            "closed_positions":len(closed),"open_positions":len(open_rows),
            "positive_closed_positions":sum(p["realized_net_raw"]>0 for p in closed),
            "skips":skips,"closed":closed,"open":open_rows,"events":events,
            "quote_source_timestamp_verified":False,"fee_semantics_verified":False,
            "portfolio_mark_to_market_verified":False,**FALSE_FLAGS}

def replay(database,*,initial_usdc=1000,stress_bps=25,hold_seconds=180,max_positions=3,limit=100,**risk):

    rows,stats=collect(database,limit)
    exits,exit_stats=collect_exits(database,rows,limit)
    return dict(simulate(rows,exit_quotes=exits,initial_usdc=initial_usdc,stress_bps=stress_bps,
                         hold_seconds=hold_seconds,max_positions=max_positions,**risk),**stats,**exit_stats)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--initial-usdc",type=int,default=1000)
    p.add_argument("--stress-bps",type=int,default=25)
    p.add_argument("--hold-seconds",type=int,default=180)
    p.add_argument("--max-positions",type=int,default=3)
    p.add_argument("--limit",type=int,default=100)
    p.add_argument("--risk-mode",action="store_true")
    p.add_argument("--stop-loss-bps",type=int,default=300)
    p.add_argument("--take-profit-bps",type=int,default=500)
    p.add_argument("--exposure-bps",type=int,default=3500)
    p.add_argument("--position-bps",type=int,default=1500)
    p.add_argument("--loss-budget-bps",type=int,default=500)
    a=p.parse_args()
    try:
        d=replay(a.database,initial_usdc=a.initial_usdc,stress_bps=a.stress_bps,
                 hold_seconds=a.hold_seconds,max_positions=a.max_positions,limit=a.limit,
                 risk_mode=a.risk_mode,stop_loss_bps=a.stop_loss_bps,take_profit_bps=a.take_profit_bps,
                 exposure_bps=a.exposure_bps,position_bps=a.position_bps,loss_budget_bps=a.loss_budget_bps)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"]=="position_replay_complete" else 2
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
