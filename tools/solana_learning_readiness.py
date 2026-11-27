"""Offline learning readiness: coverage and cost sensitivity, never train or promote."""
import argparse
import json
import sqlite3
from bisect import bisect_left,bisect_right
from collections import Counter,defaultdict
from datetime import timedelta
from tools.solana_paper_replay import collect,instant,FALSE_FLAGS
from tools.solana_strategy_lab import compare

STRESS_LEVELS=(25,50,100)

def coverage(rows,*,horizon_seconds=180,max_wait_seconds=3600):
    if type(horizon_seconds) is not int or type(max_wait_seconds) is not int or not 60<=horizon_seconds<=max_wait_seconds<=86400:
        raise ValueError("Invalid coverage horizon")
    counts=Counter((r["mint"],instant(r["timestamp"])) for r in rows)
    exact=defaultdict(list)
    by_mint=defaultdict(list)
    usable=[]
    for r in rows:
        stamp=instant(r["timestamp"])
        if counts[(r["mint"],stamp)]!=1:continue
        usable.append((r,stamp))
        exact[(r["mint"],r["token_amount_raw"])].append(stamp)
        by_mint[r["mint"]].append(stamp)
    for group in (exact,by_mint):
        for values in group.values():values.sort()
    matched=0;wrong_quantity=0;missing=0;censored=0
    end=max((stamp for _,stamp in usable),default=None)
    for r,stamp in usable:
        start=stamp+timedelta(seconds=horizon_seconds)
        deadline=stamp+timedelta(seconds=max_wait_seconds)
        # Right-censored entries are not counted as failures.
        if deadline>end:
            censored+=1;continue
        def exists(values):
            return bisect_left(values,start)<bisect_right(values,deadline)
        if exists(exact[(r["mint"],r["token_amount_raw"])]):matched+=1
        elif exists(by_mint[r["mint"]]):wrong_quantity+=1
        else:missing+=1
    eligible=matched+wrong_quantity+missing
    return {"observations":len(rows),"ambiguous_observations":len(rows)-len(usable),
            "eligible_entries":eligible,"exact_quantity_matches":matched,
            "different_quantity_only":wrong_quantity,"no_later_mint_quote":missing,
            "right_censored_entries":censored,
            "exact_match_pct":round(100*matched/eligible,4) if eligible else None,
            "minimum_horizon_seconds":horizon_seconds,"maximum_wait_seconds":max_wait_seconds,
            "coverage_is_execution_verified":False}

def evaluate(rows,*,initial_usdc=1000):
    results=[compare(rows,initial_usdc=initial_usdc,stress_bps=bps) for bps in STRESS_LEVELS]
    first=results[0]
    cut=instant(first["split_timestamp"]) if first["split_timestamp"] else None
    earlier=[r for r in rows if cut is not None and instant(r["timestamp"])<cut]
    later=[r for r in rows if cut is not None and instant(r["timestamp"])>=cut]
    cov={"full_history":coverage(rows),"earlier_window":coverage(earlier),"later_window":coverage(later)}
    blockers=["quote_timestamps_not_independently_verified","execution_and_depth_not_verified",
              "no_independent_holdout","exact_quantity_coverage_not_execution_evidence"]
    if not all(r["sample_gate_met"] for r in results):
        blockers.append("insufficient_comparable_policy_samples")
    if any(cov[w]["eligible_entries"]==0 for w in ("earlier_window","later_window")):
        blockers.append("insufficient_mature_exit_observations")
    if any(cov[w]["different_quantity_only"] or cov[w]["no_later_mint_quote"] for w in ("earlier_window","later_window")):
        blockers.append("incomplete_exit_quote_coverage")
    scenarios=[]
    for result in results:
        scenarios.append({"stress_bps_per_direction":result["stress_bps_per_direction"],
                          "sample_gate_met":result["sample_gate_met"],
                          "policies":[{"policy":r["policy"],
                                       "earlier_window":r["earlier_window"],
                                       "later_window":r["later_window"]} for r in result["policies"]]})
    return {"status":"learning_readiness_report_complete","research_only":True,"network_requests":False,
            "dataset_sha256":first["dataset_sha256"],"observation_count":len(rows),
            "split_timestamp":first["split_timestamp"],"source_scope":"dexterm_bridge_only",
            "coverage":cov,"cost_scenarios":scenarios,"blockers":blockers,
            "training_allowed":False,"training_performed":False,"weights_updated":False,
            "winner":None,"model_promoted":False,"independent_holdout_verified":False,**FALSE_FLAGS}

def run(database,*,initial_usdc=1000,limit=100):
    rows,stats=collect(database,limit)
    result=dict(evaluate(rows,initial_usdc=initial_usdc),**stats)
    if stats["bridge_history_truncated"]:result["blockers"].append("archive_window_truncated")
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--initial-usdc",type=int,default=1000)
    p.add_argument("--limit",type=int,default=100)
    a=p.parse_args()
    try:
        print(json.dumps(run(a.database,initial_usdc=a.initial_usdc,limit=a.limit),indent=2,allow_nan=False))
        return 0
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,"training_allowed":False,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
