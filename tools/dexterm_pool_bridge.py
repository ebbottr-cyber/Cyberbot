"""Bounded mint-to-USDC pool diagnostics from an archived DexTerm scan."""
import argparse,json,os,time
from pathlib import Path
from urllib.parse import urlencode
import httpx
from cyberbot.observed_pilot import PilotError
from tools.dexterm_candidate_review import review,MAX_BYTES
from tools.solana_pool_discovery import DEX,fetch,dex_rows,candidates
from tools.solana_public_scan import run as scan,REFERENCE_MINTS,reference_conflict
from tools.solana_public_snapshot import run as snapshot

FLAGS={"security_verified":False,"meme_classification_verified":False,
       "token_identity_verified":False,"depth_verified":False,
       "live_data_verified":False,"pilot_applied":False,"real_orders":False}

def match_pool(raw,mint):
    if not isinstance(raw,dict) or not isinstance(raw.get("pairs"),list):
        raise ValueError("Malformed pool search response")
    exact=[r for r in dex_rows(raw) if r[0]==mint]
    pools=[p for p in candidates(exact) if not reference_conflict(p)]
    return pools[0] if pools else None

def lookup(client,mint):
    return match_pool(fetch(client,DEX+urlencode({"q":mint})),mint)

def run(report,*,lookup_limit=3,lookup_fn=lookup,inspect=snapshot,sleep=time.sleep):
    if os.getenv("CYBERBOT_PILOT_KILL_SWITCH")!="1":
        raise PilotError("Kill switch must be active")
    if os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise PilotError("Explicit data usage permission required")
    if type(lookup_limit) is not int or not 1<=lookup_limit<=3:
        raise PilotError("Lookup limit 1 to 3")
    reviewed=review(report)
    refs=set(REFERENCE_MINTS.values())
    novel=[m for m in reviewed["shortlist_mints"] if m not in refs]
    selected=novel[:lookup_limit]
    result={"status":"no_nonreference_candidates","source":"dexterm_historical_shortlist_exact_mint_lookup",
            "shortlist_count":reviewed["shortlist_count"],"nonreference_shortlist_count":len(novel),
            "lookup_limit":lookup_limit,"remaining_mints":novel[lookup_limit:],
            "lookups":[],"matched_pool_count":0,"scan":None,**FLAGS}
    if not selected:return result
    pools=[]
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as c:
        for i,mint in enumerate(selected):
            if i:sleep(3)
            try:
                row=lookup_fn(c,mint)
            except httpx.HTTPStatusError as e:
                result["lookups"].append({"mint":mint,"status":"provider_http_error","http_status":e.response.status_code})
                result["status"]="lookup_partial"
                result["remaining_mints"]=selected[i+1:]+novel[lookup_limit:]
                return result
            except (ValueError,TypeError,KeyError,AttributeError,OSError,ArithmeticError,httpx.HTTPError) as e:
                result["lookups"].append({"mint":mint,"status":"lookup_rejected","error_type":type(e).__name__})
                result["status"]="lookup_partial"
                result["remaining_mints"]=selected[i+1:]+novel[lookup_limit:]
                return result
            result["lookups"].append({"mint":mint,"status":"reported_pool_match" if row else "no_eligible_direct_usdc_pool","pool":row})
            if row:
                pools.append(row)
                result["matched_pool_count"]=len(pools)
    if not pools:
        result["status"]="no_eligible_pools"
        return result
    sleep(3)
    diagnostics=scan(limit=1,max_candidates=len(pools),discoverer=lambda:pools,inspect=inspect,sleep=sleep)
    diagnostics["scope"]="dexterm_shortlist_dexscreener_exact_mint_direct_usdc"
    result["scan"]=diagnostics
    result["status"]="diagnostic_complete" if diagnostics["target_reached"] else "diagnostic_partial"
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report",required=True)
    p.add_argument("--lookup-limit",type=int,default=3)
    a=p.parse_args()
    try:
        with Path(a.report).open("rb") as f:
            data=f.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError("Report exceeds size limit")
        d=run(json.loads(data.decode("utf-8-sig")),lookup_limit=a.lookup_limit)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"]=="diagnostic_complete" else 2 if d["status"] in ("no_eligible_pools","no_nonreference_candidates") else 1
    except (ValueError,TypeError,KeyError,OSError,ArithmeticError,AttributeError,httpx.HTTPError) as e:
        print(json.dumps({"status":"rejected","reason":str(e) if isinstance(e,PilotError) else type(e).__name__,**FLAGS}))
        return 1
if __name__=="__main__":raise SystemExit(main())
