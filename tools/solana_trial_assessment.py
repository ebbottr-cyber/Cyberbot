"""Read-only multi-day research trial assessment; no fit, orders, or deployment."""
import argparse
import json
import sqlite3
from datetime import datetime,timezone,timedelta
from tools.solana_paper_replay import collect,instant,FALSE_FLAGS
from tools.solana_exit_history import collect_exits,bound
from tools.solana_paper_positions import simulate
from tools.solana_learning_readiness import coverage,STRESS_LEVELS
from tools.solana_learning_dataset import build
from tools.solana_model_experiment import MIN_EARLIER,MIN_LATER,MIN_CLASS,MIN_MINTS

MIN_DAYS=7
MIN_ACTIVE_DAYS=5
MIN_CLOSED=100
MIN_DISTINCT_MINTS=10
MIN_MATURE=100
MIN_COVERAGE_PCT=80
MAX_DAYS=14

def day_metrics(rows,exits):
    exits=bound(rows,exits)
    cov=coverage(rows,exit_quotes=exits)
    scenarios=[]
    for bps in STRESS_LEVELS:
        paper=simulate(rows,exit_quotes=exits,initial_usdc=1000,risk_mode=True,
                       hold_seconds=300,stress_bps=bps)
        closed=paper["closed"]
        # Drawdown on realized P/L only. Not portfolio mark-to-market.
        net=peak=drawdown=0
        for x in closed:
            net+=x["realized_net_raw"];peak=max(peak,net)
            drawdown=max(drawdown,peak-net)
        gains=sum(max(0,x["realized_net_raw"]) for x in closed)
        losses=sum(max(0,-x["realized_net_raw"]) for x in closed)
        scenarios.append({"stress_bps_per_direction":bps,"closed_positions":len(closed),
                          "open_positions":paper["open_positions"],
                          "positive_closed_positions":paper["positive_closed_positions"],
                          "realized_net_raw":paper["realized_net_raw"],
                          "gross_gain_raw":gains,"gross_loss_raw":losses,
                          "closed_only_profit_factor":round(gains/losses,6) if losses else None,
                          "realized_only_drawdown_raw":drawdown,
                          "final_equity_raw":paper["final_equity_raw"],
                          "entry_halted":paper["entry_halted"],
                          "exit_reason_counts":paper["exit_reason_counts"]})
    ds=build(rows,exit_quotes=exits)
    partitions=ds["partitions"]
    sufficient=all(partitions[name]["examples"]>=n and
                   min(partitions[name]["positive_labels"],partitions[name]["nonpositive_labels"])>=MIN_CLASS and
                   partitions[name]["unique_mints"]>=MIN_MINTS
                   for name,n in (("earlier",MIN_EARLIER),("later",MIN_LATER)))
    return {"observations":len(rows),"unique_mints":len({r["mint"] for r in rows}),
            "distinct_observation_times":len({instant(r["timestamp"]) for r in rows}),
            "first_observation_utc":min((instant(r["timestamp"]) for r in rows),default=None).isoformat() if rows else None,
            "last_observation_utc":max((instant(r["timestamp"]) for r in rows),default=None).isoformat() if rows else None,
            "coverage":cov,"bound_exit_quotes":len(exits),"scenarios":scenarios,
            "dataset_examples":ds["example_count"],"partitions":partitions,
            "daily_model_sample_gate_met":sufficient}

def run(database,*,start,end,limit=500,now=None):
    now=datetime.now(timezone.utc) if now is None else now
    start,end=instant(start),instant(end)
    if now.tzinfo is None or end>now:raise ValueError("Trial must end in the past")
    if any((x.hour,x.minute,x.second,x.microsecond)!=(0,0,0,0) for x in (start,end)):
        raise ValueError("UTC midnight boundaries required")
    days=(end-start).days
    if not 1<=days<=MAX_DAYS:raise ValueError("Trial duration must be 1 to 14 days")
    if type(limit) is not int or not 1<=limit<=500:raise ValueError("Invalid per-day report limit")
    daily=[];mints=set();mature=matched=0;active=0;truncated=False
    total_closed={b:0 for b in STRESS_LEVELS}
    unresolved={b:0 for b in STRESS_LEVELS}
    for i in range(days):
        a=start+timedelta(days=i);b=a+timedelta(days=1)
        window=(a.isoformat(),b.isoformat())
        rows,stats=collect(database,limit,window=window)
        exits,es=collect_exits(database,rows,limit,window=window)
        # Import windows alone do not prove observation timestamps. A late
        # imported quote must not leak across a declared evaluation boundary.
        selected=[r for r in rows if a<=instant(r["timestamp"])<b]
        selected_exits=[q for q in exits if a<=instant(q["timestamp"])<b]
        data=day_metrics(selected,selected_exits)
        incomplete=stats["bridge_history_truncated"] or es["exit_history_truncated"]
        truncated=truncated or incomplete
        data.update(day=a.date().isoformat(),archive_truncated=incomplete,
                    observations_outside_day=len(rows)-len(selected),
                    exit_quotes_outside_day=len(exits)-len(selected_exits))
        daily.append(data)
        if incomplete:continue
        if selected:active+=1
        mints.update(r["mint"] for r in selected)
        cov=data["coverage"];mature+=cov["eligible_entries"];matched+=cov["exact_quantity_matches"]
        for scenario in data["scenarios"]:
            cost=scenario["stress_bps_per_direction"]
            total_closed[cost]+=scenario["closed_positions"]
            unresolved[cost]+=scenario["open_positions"]
    pct=round(100*matched/mature,4) if mature else None
    blockers=[]
    if days<MIN_DAYS:blockers.append("minimum_trial_days")
    if active<MIN_ACTIVE_DAYS:blockers.append("minimum_days_with_observations")
    if truncated:blockers.append("archive_window_truncated")
    if len(mints)<MIN_DISTINCT_MINTS:blockers.append("minimum_token_diversity")
    if mature<MIN_MATURE or pct is None or pct<MIN_COVERAGE_PCT:blockers.append("insufficient_mature_exit_coverage")
    if min(total_closed.values())<MIN_CLOSED:blockers.append("insufficient_closed_positions")
    if any(unresolved.values()):blockers.append("unvalued_open_positions")
    return {"status":"trial_sample_gate_met" if not blockers else "trial_evidence_insufficient",
            "research_only":True,"network_requests":False,
            "start_utc":start.isoformat(),"end_utc_exclusive":end.isoformat(),"days_requested":days,
            "days_with_observations_in_complete_windows":active,
            "complete_windows_unique_mints":len(mints),"mature_entries":mature,"exact_quantity_matches":matched,
            "exact_match_pct":pct,"coverage_is_execution_verified":False,
            "closed_counts_by_cost":total_closed,"unresolved_counts_by_cost":unresolved,
            "thresholds":{"minimum_days":MIN_DAYS,"minimum_active_days":MIN_ACTIVE_DAYS,
                          "minimum_closed_positions_per_cost":MIN_CLOSED,"minimum_unique_mints":MIN_DISTINCT_MINTS,
                          "minimum_mature_entries":MIN_MATURE,"minimum_exact_match_pct":MIN_COVERAGE_PCT},
            "daily":daily,"blockers":blockers,"simulation_policy":"fixed_balanced_exit_v1",
            "initial_usdc_per_day_per_scenario":1000,
            "daily_flat_reset":True,"cross_day_positions_carried":False,
            "cross_day_returns_compounded":False,"continuous_uptime_verified":False,
            "independent_holdout_verified":False,"production_training_performed":False,
            "training_allowed":False,"weights_updated":False,"model_promoted":False,
            "portfolio_mark_to_market_verified":False,**FALSE_FLAGS}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--start",required=True)
    p.add_argument("--end",required=True)
    p.add_argument("--limit",type=int,default=500)
    a=p.parse_args()
    try:
        out=run(a.database,start=a.start,end=a.end,limit=a.limit)
        print(json.dumps(out,indent=2,allow_nan=False))
        return 0 if out["status"]=="trial_sample_gate_met" else 2
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"trial_rejected","error_type":type(e).__name__,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
