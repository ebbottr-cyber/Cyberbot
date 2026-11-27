"""Bounded foreground public pool scan; diagnostics only, never trade signals."""
import argparse,json,os,time
import httpx
from urllib.parse import urlencode
from cyberbot.observed_pilot import utc,PilotError
from tools.solana_pool_discovery import GECKO,DEX,QUERIES,fetch,gecko_rows,dex_rows,candidates
from tools.solana_public_snapshot import run as snapshot

def discover(*,sleep=time.sleep):
    # Bounded public discovery, not a comprehensive market universe.
    sources=[(GECKO+"trending_pools?page=1",gecko_rows),
             (GECKO+"pools?page=1",gecko_rows)]
    sources += [(DEX+urlencode({"q":q}),dex_rows) for q in QUERIES]
    rows=[]
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as c:
        for i,(url,parse) in enumerate(sources):
            if i:sleep(2)
            try:rows.extend(list(parse(fetch(c,url))))
            except httpx.HTTPStatusError as e:
                raise PilotError("Discovery HTTP "+str(e.response.status_code)+"; no_retry") from None
    return candidates(rows)

def run(*,limit=2,max_candidates=None,discoverer=discover,inspect=snapshot,sleep=time.sleep):
    if os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise PilotError("Explicit data usage permission required")
    if type(limit) is not int or not 1<=limit<=3:
        raise PilotError("Scan limit 1 to 3")
    max_candidates=limit if max_candidates is None else max_candidates
    if type(max_candidates) is not int or not limit<=max_candidates<=8:
        raise PilotError("Candidate budget must be between target and 8")
    pools=discoverer()
    selected=[];seen=set()
    for row in pools:
        mint=row["mint"]
        if mint in seen:continue
        seen.add(mint);selected.append(row)
        if len(selected)>=max_candidates:break
    reports=[]
    for i,row in enumerate(selected):
        if i:sleep(10)
        try:
            report=inspect(row["mint"],row["pool"])
            reports.append({"candidate":row,"diagnostic":report})
            if report.get("status") not in ("diagnostic_complete","diagnostic_unsupported_mint"):break
            if sum(r["diagnostic"].get("status")=="diagnostic_complete" for r in reports)>=limit:break
        except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AttributeError,httpx.HTTPError) as e:
            reports.append({"candidate":row,"diagnostic":{"status":"rejected","reason":str(e) if isinstance(e,PilotError) else type(e).__name__}})
            break
    done=sum(r["diagnostic"].get("status")=="diagnostic_complete" for r in reports)
    skipped=sum(r["diagnostic"].get("status")=="diagnostic_unsupported_mint" for r in reports)
    target_reached=done>=limit
    exhausted=bool(selected) and (target_reached or len(reports)==len(selected)) and done+skipped==len(reports)
    status=("scan_no_candidates" if not selected else "scan_partial" if not exhausted else
            "scan_no_supported_candidates" if not done else "scan_complete_with_skips" if skipped else "scan_complete")
    return {"status":status,"completed_mints":done,"unsupported_mints":skipped,
            "retrieved_at":utc().isoformat(),"scope":"geckoterminal_trending_and_top_page_1_plus_dex_search_direct_usdc",
            "target_completed_mints":limit,"target_reached":target_reached,"max_candidates":max_candidates,
            "available_pools":len(pools),"selected_mints":len(selected),"inspected_mints":len(reports),
            "reports":reports,"meme_classification_verified":False,"security_verified":False,
            "depth_verified":False,"route_integrity_verified":False,"live_data_verified":False,
            "pilot_applied":False,"real_orders":False,"api_key_used":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit",type=int,default=2);p.add_argument("--max-candidates",type=int);a=p.parse_args()
    try:
        d=run(limit=a.limit,max_candidates=a.max_candidates)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"] in ("scan_complete","scan_complete_with_skips") else 2 if d["status"] in ("scan_no_candidates","scan_no_supported_candidates") else 1
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AttributeError,httpx.HTTPError) as e:
        print(json.dumps({"status":"rejected","reason":str(e) if isinstance(e,PilotError) else type(e).__name__,"pilot_applied":False,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
