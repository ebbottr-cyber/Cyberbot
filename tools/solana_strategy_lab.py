"""Offline fixed-policy comparison, independent paper balances, no model promotion."""
import argparse
import hashlib
import json
import sqlite3
from tools.solana_paper_positions import simulate
from tools.solana_paper_replay import collect,instant,FALSE_FLAGS

# Predeclared research hypotheses, not calibrated or recommended settings.
POLICIES=(
    ("time_baseline",{"risk_mode":False,"hold_seconds":180}),
    ("tight_exit",{"risk_mode":True,"hold_seconds":180,"stop_loss_bps":200,"take_profit_bps":300}),
    ("balanced_exit",{"risk_mode":True,"hold_seconds":300,"stop_loss_bps":300,"take_profit_bps":500}),
    ("longer_exit",{"risk_mode":True,"hold_seconds":900,"stop_loss_bps":500,"take_profit_bps":800}),
)
MIN_CLOSED=30
MIN_MINTS=5

def summary(rows,settings,capital,stress):
    r=simulate(rows,initial_usdc=capital,stress_bps=stress,max_positions=3,**settings)
    closed=r["closed"]
    n=len(closed)
    mints=len({x["mint"] for x in closed})
    return {"closed_positions":n,"open_positions":r["open_positions"],
            "closed_unique_mints":mints,"positive_closed_positions":r["positive_closed_positions"],
            "realized_net_raw":r["realized_net_raw"],"available_cash_raw":r["available_cash_raw"],
            "open_cost_basis_raw":r["open_cost_basis_raw"],"final_equity_raw":r["final_equity_raw"],
            "gross_realized_loss_raw":r["gross_realized_loss_raw"],"entry_halted":r["entry_halted"],
            "exit_reason_counts":r["exit_reason_counts"],"skips":r["skips"],
            "sample_threshold_met":n>=MIN_CLOSED and mints>=MIN_MINTS,
            "complete_equity_available":r["final_equity_raw"] is not None,
            "win_rate_pct":round(100*r["positive_closed_positions"]/n,4) if n else None}

def compare(rows,*,initial_usdc=1000,stress_bps=25):
    ordered=sorted(rows,key=lambda r:(instant(r["timestamp"]),r["mint"],r["source_digest"],r["source_index"]))
    times=sorted({instant(r["timestamp"]) for r in ordered})
    # Fixed 70/30 split by distinct observation times. Entire timestamp batches
    # stay together. Each window starts flat, with identical independent capital.
    cut=times[max(1,len(times)*7//10)] if len(times)>=2 else None
    early=[r for r in ordered if cut is not None and instant(r["timestamp"])<cut]
    late=[r for r in ordered if cut is not None and instant(r["timestamp"])>=cut]
    fingerprint=hashlib.sha256(json.dumps(ordered,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    results=[]
    for name,settings in POLICIES:
        whole=summary(ordered,settings,initial_usdc,stress_bps)
        first=summary(early,settings,initial_usdc,stress_bps)
        second=summary(late,settings,initial_usdc,stress_bps)
        results.append({"policy":name,"settings":dict(settings),"full_history":whole,
                        "earlier_window":first,"later_window":second})
    enough=bool(cut) and all(r[w]["sample_threshold_met"] and r[w]["complete_equity_available"]
                           for r in results for w in ("earlier_window","later_window"))
    return {"status":"comparison_complete" if ordered else "no_usable_quotes",
            "evidence_status":"exploratory_comparison_only" if enough else "insufficient_comparable_evidence",
            "research_only":True,"network_requests":False,"policy_version":1,
            "initial_usdc_per_policy_per_window":initial_usdc,"stress_bps_per_direction":stress_bps,
            "sample_gate":{"minimum_closed_positions_per_window":MIN_CLOSED,"minimum_closed_unique_mints_per_window":MIN_MINTS,
                           "requires_no_unvalued_open_positions":True},
            "sample_gate_met":enough,"observation_count":len(ordered),"distinct_observation_times":len(times),
            "dataset_sha256":fingerprint,"split_timestamp":cut.isoformat() if cut else None,
            "earlier_observations":len(early),"later_observations":len(late),
            "split_method":"70_30_distinct_timestamps_flat_reset_no_carry",
            "policies":results,"winner":None,"automatic_model_selection":False,
            "weights_updated":False,"independent_holdout_verified":False,
            "fee_semantics_verified":False,"quote_source_timestamp_verified":False,**FALSE_FLAGS}

def run(database,*,initial_usdc=1000,stress_bps=25,limit=100):
    rows,stats=collect(database,limit)
    return dict(compare(rows,initial_usdc=initial_usdc,stress_bps=stress_bps),**stats)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--initial-usdc",type=int,default=1000)
    p.add_argument("--stress-bps",type=int,default=25)
    p.add_argument("--limit",type=int,default=100)
    a=p.parse_args()
    try:
        d=run(a.database,initial_usdc=a.initial_usdc,stress_bps=a.stress_bps,limit=a.limit)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"]=="comparison_complete" else 2
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
