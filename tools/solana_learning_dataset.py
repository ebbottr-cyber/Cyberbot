"""Build quote-derived research examples, not executable signals or training authorization."""
import argparse
import hashlib
import json
import sqlite3
from bisect import bisect_left
from collections import Counter,defaultdict
from datetime import timedelta
from tools.solana_paper_replay import collect,instant,fee,FALSE_FLAGS
from tools.solana_exit_history import bound,collect_exits

FEATURE_NAMES=("entry_input_raw","entry_roundtrip_bps","previous_buy_price_change_bps","previous_observation_gap_seconds")
HORIZON=180
MAX_WAIT=3600

def bps(n,d):
    # Signed integer arithmetic with floor rounding; no floating point prices.
    if d<=0:raise ValueError("Invalid denominator")
    return n*10000//d

def build(rows,*,stress_bps=25,exit_quotes=()):
    if type(stress_bps) is not int or not 0<=stress_bps<=1000:
        raise ValueError("Invalid stress assumption")
    ordered=sorted(rows,key=lambda r:(instant(r["timestamp"]),r["mint"],r["source_digest"],r["source_index"]))
    counts=Counter((r["mint"],instant(r["timestamp"])) for r in ordered)
    usable=[r for r in ordered if counts[(r["mint"],instant(r["timestamp"]))]==1]
    times=sorted({instant(r["timestamp"]) for r in usable})
    cut=times[max(1,len(times)*7//10)] if len(times)>=2 else None
    exits=bound(usable,exit_quotes)
    end=max(times+[instant(r["timestamp"]) for r in exits],default=None)
    explicit=defaultdict(list)
    for r in exits:explicit[(r["entry_source_digest"],r["entry_source_index"])].append(r)
    groups=defaultdict(list)
    previous={}
    for r in usable:
        groups[(r["mint"],r["token_amount_raw"])].append(r)
    stamps={key:[instant(r["timestamp"]) for r in group] for key,group in groups.items()}
    examples=[];skips=Counter()
    for r in usable:
        mint=r["mint"];now=instant(r["timestamp"]);old=previous.get(mint)
        previous[mint]=r
        n=r["input_raw"];qty=r["token_amount_raw"]
        if min(n,qty,r["return_raw"])<=0:raise ValueError("Invalid quote amounts")
        if old is None:
            skips["no_prior_observation"]+=1;continue
        gap=(now-instant(old["timestamp"])).total_seconds()
        if not 0<gap<=MAX_WAIT:
            skips["prior_observation_too_old"]+=1;continue
        if cut is None or now+timedelta(seconds=MAX_WAIT)>end:
            skips["right_censored"]+=1;continue
        # Earlier labels must finish within the earlier window, including
        # their entire eligibility window. This purges boundary overlap.
        partition="earlier" if now<cut else "later"
        if partition=="earlier" and now+timedelta(seconds=MAX_WAIT)>=cut:
            skips["split_boundary_purged"]+=1;continue
        key=(mint,qty);group=groups[key]
        i=bisect_left(stamps[key],now+timedelta(seconds=HORIZON))
        candidates=list(explicit[(r["source_digest"],r["source_index"])])
        if i<len(group) and stamps[key][i]<=now+timedelta(seconds=MAX_WAIT):candidates.append(group[i])
        if not candidates:
            skips["no_exact_quantity_exit"]+=1;continue
        exit_time=min(instant(q["timestamp"]) for q in candidates)
        first=[q for q in candidates if instant(q["timestamp"])==exit_time]
        if len({q["return_raw"] for q in first})!=1:
            skips["ambiguous_first_exit"]+=1;continue
        exit_row=sorted(first,key=lambda q:(not q.get("exit_only",False),q["source_digest"],q["source_index"]))[0]
        features={"entry_input_raw":n,
                  "entry_roundtrip_bps":bps(r["return_raw"]-n,n),
                  "previous_buy_price_change_bps":bps(n*old["token_amount_raw"]-old["input_raw"]*qty,old["input_raw"]*qty),
                  "previous_observation_gap_seconds":int(gap)}
        entry_total=n+fee(n,stress_bps)
        received=exit_row["return_raw"]
        net=received-fee(received,stress_bps)-entry_total
        examples.append({"mint":mint,"partition":partition,"feature_at":now.isoformat(),
                         "label_at":exit_time.isoformat(),"features":features,
                         "label":{"quote_net_raw":net,"quote_net_bps":bps(net,entry_total),"positive_quote_net":net>0},
                         "entry_source":{"digest":r["source_digest"],"index":r["source_index"]},
                         "exit_source":{"digest":exit_row["source_digest"],"index":exit_row["source_index"]}})
    partitions={}
    for name in ("earlier","later"):
        subset=[r for r in examples if r["partition"]==name]
        partitions[name]={"examples":len(subset),"unique_mints":len({r["mint"] for r in subset}),
                          "positive_labels":sum(r["label"]["positive_quote_net"] for r in subset),
                          "nonpositive_labels":sum(not r["label"]["positive_quote_net"] for r in subset)}
    digest=hashlib.sha256(json.dumps(examples,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return {"status":"dataset_built" if examples else "no_labeled_examples",
            "source_scope":"dexterm_bridge_only","research_only":True,"network_requests":False,
            "feature_schema_version":1,"feature_names":list(FEATURE_NAMES),"label_type":"future_exact_quantity_reported_quote_after_cost_stress",
            "horizon_seconds":HORIZON,"maximum_wait_seconds":MAX_WAIT,"stress_bps_per_direction":stress_bps,
            "split_timestamp":cut.isoformat() if cut else None,"split_method":"chronological_70_30_full_label_window_purge",
            "observation_count":len(rows),"ambiguous_observations":len(rows)-len(usable),
            "skipped":dict(skips),"partitions":partitions,"example_count":len(examples),
            "dataset_sha256":digest,"examples":examples,"training_allowed":False,
            "training_performed":False,"weights_updated":False,"model_promoted":False,
            "labels_are_real_fills":False,"independent_holdout_verified":False,
            "quote_source_timestamp_verified":False,"overlapping_examples_possible":True,**FALSE_FLAGS}

def run(database,*,limit=500,stress_bps=25):
    rows,stats=collect(database,limit)
    exits,exit_stats=collect_exits(database,rows,limit)
    return dict(build(rows,stress_bps=stress_bps,exit_quotes=exits),**stats,**exit_stats)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--limit",type=int,default=500)
    p.add_argument("--stress-bps",type=int,default=25)
    a=p.parse_args()
    try:
        print(json.dumps(run(a.database,limit=a.limit,stress_bps=a.stress_bps),indent=2,allow_nan=False))
        return 0
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError,OSError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,"training_allowed":False,**FALSE_FLAGS}))
        return 1

if __name__=="__main__":raise SystemExit(main())
