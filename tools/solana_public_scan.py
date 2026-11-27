"""Bounded foreground public pool scan; diagnostics only, never trade signals."""
import argparse,json,os,time
import httpx
from cyberbot.observed_pilot import utc,PilotError
from tools.solana_pool_discovery import GECKO,fetch,gecko_rows,candidates
from tools.solana_public_snapshot import run as snapshot

def discover():
    # One bounded page of trending pools, not a comprehensive market universe.
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as c:
        return candidates(gecko_rows(fetch(c,GECKO+"trending_pools?page=1")))

def run(*,limit=2,discoverer=discover,inspect=snapshot,sleep=time.sleep):
    if os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise PilotError("Explicit data usage permission required")
    if type(limit) is not int or not 1<=limit<=3:
        raise PilotError("Scan limit 1 to 3")
    pools=discoverer()
    selected=[];seen=set()
    for row in pools:
        mint=row["mint"]
        if mint in seen:continue
        seen.add(mint);selected.append(row)
        if len(selected)>=limit:break
    reports=[]
    for i,row in enumerate(selected):
        if i:sleep(10)
        try:
            report=inspect(row["mint"],row["pool"])
            reports.append({"candidate":row,"diagnostic":report})
            if report.get("status")!="diagnostic_complete":break
        except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AttributeError,httpx.HTTPError) as e:
            reports.append({"candidate":row,"diagnostic":{"status":"rejected","reason":str(e) if isinstance(e,PilotError) else type(e).__name__}})
            break
    complete=bool(selected) and len(reports)==len(selected) and all(r["diagnostic"].get("status")=="diagnostic_complete" for r in reports)
    return {"status":"scan_complete" if complete else "scan_no_candidates" if not selected else "scan_partial",
            "retrieved_at":utc().isoformat(),"scope":"geckoterminal_trending_page_1_direct_usdc",
            "available_pools":len(pools),"selected_mints":len(selected),"inspected_mints":len(reports),
            "reports":reports,"meme_classification_verified":False,"security_verified":False,
            "depth_verified":False,"route_integrity_verified":False,"live_data_verified":False,
            "pilot_applied":False,"real_orders":False,"api_key_used":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit",type=int,default=2);a=p.parse_args()
    try:
        d=run(limit=a.limit)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"]=="scan_complete" else 2 if d["status"]=="scan_no_candidates" else 1
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AttributeError,httpx.HTTPError) as e:
        print(json.dumps({"status":"rejected","reason":str(e) if isinstance(e,PilotError) else type(e).__name__,"pilot_applied":False,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
