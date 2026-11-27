"""Bounded foreground public pool scan; diagnostics only, never trade signals."""
import argparse,json,os,time
import httpx
from urllib.parse import urlencode
from cyberbot.observed_pilot import utc,PilotError
from cyberbot.solana_pilot import address
from tools.solana_pool_discovery import GECKO,DEX,QUERIES,fetch,gecko_rows,dex_rows,candidates
from tools.solana_public_snapshot import run as snapshot

# Narrow, reviewed reference identities; not a general verification registry.
# POPCAT reference: https://www.bitcoin.com/price/popcat/
# BONK reference: previously exercised diagnostic mint, not an endorsement.
REFERENCE_MINTS={"POPCAT":"7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
                 "BONK":"DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"}

# Native SOL wrapper is a routing asset, not a meme candidate.
NON_TARGET_MINTS={"So11111111111111111111111111111111111111112":"wrapped_sol"}

def reference_conflict(row):
    label=str(row.get("label","")).split("/",1)[0].strip().upper()
    expected=REFERENCE_MINTS.get(label)
    return expected if expected and row["mint"]!=expected else None

def discover(*,sleep=time.sleep):
    # Bounded public discovery, not a comprehensive market universe.
    sources=[(GECKO+"trending_pools?page=1",gecko_rows),
             (GECKO+"pools?page=1",gecko_rows)]
    sources += [(DEX+urlencode({"q":REFERENCE_MINTS.get(q.split("/",1)[0],q)}),dex_rows) for q in QUERIES]
    rows=[]
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as c:
        for i,(url,parse) in enumerate(sources):
            if i:sleep(2)
            try:rows.extend(list(parse(fetch(c,url))))
            except httpx.HTTPStatusError as e:
                raise PilotError("Discovery HTTP "+str(e.response.status_code)+"; no_retry") from None
    # Retain one best eligible pool for each reference even if the general
    # liquidity-ranked top 20 would otherwise crowd it out.
    general=candidates(rows)
    reference_rows=[r for r in rows if r[0] in REFERENCE_MINTS.values()]
    refs=candidates(reference_rows)
    best={}
    for row in refs:best.setdefault(row["mint"],row)
    retained=list(best.values())
    # Keep general order here; reference priority is an explicit scan option.
    merged=general+[r for r in retained if (r["mint"],r["pool"]) not in {(x["mint"],x["pool"]) for x in general}]
    return merged

def run(*,limit=2,max_candidates=None,reference_first=False,exclude_mints=(),discoverer=discover,inspect=snapshot,sleep=time.sleep):
    if os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise PilotError("Explicit data usage permission required")
    if type(limit) is not int or not 1<=limit<=3:
        raise PilotError("Scan limit 1 to 3")
    max_candidates=limit if max_candidates is None else max_candidates
    if type(max_candidates) is not int or not limit<=max_candidates<=8:
        raise PilotError("Candidate budget must be between target and 8")
    references=set(REFERENCE_MINTS.values())
    if not isinstance(exclude_mints,(tuple,list)) or len(exclude_mints)>8 or any(not address(m) or m in references for m in exclude_mints):
        raise PilotError("Invalid temporary exclusions or reference mint exclusion")
    excluded=set(exclude_mints)
    pools=discoverer()
    selected=[];seen=set();conflicts=[];excluded_found=set();non_targets=[]
    for row in pools:
        if row["mint"] in NON_TARGET_MINTS:
            non_targets.append({"mint":row["mint"],"pool":row["pool"],"label":row.get("label"),"reason":NON_TARGET_MINTS[row["mint"]]})
            continue
        expected=reference_conflict(row)
        if expected:
            conflicts.append({"mint":row["mint"],"pool":row["pool"],"label":row.get("label"),
                              "expected_reference_mint":expected,"reason":"known_label_mint_mismatch"})
            continue
        mint=row["mint"]
        if mint in excluded:
            excluded_found.add(mint);continue
        if mint in seen:continue
        seen.add(mint);selected.append(row)
    if reference_first:selected.sort(key=lambda row:row["mint"] not in references)
    eligible=selected[:]
    selected=selected[:max_candidates]
    reports=[];quote_rejections=0;holder_rejections=0;stop_reason=None
    for i,row in enumerate(selected):
        if i:sleep(10)
        try:
            report=inspect(row["mint"],row["pool"])
            reports.append({"candidate":row,"diagnostic":report})
            if report.get("status")=="diagnostic_holder_percentages_invalid":
                holder_rejections+=1
                # Only a specifically identified data inconsistency is skippable.
                if holder_rejections>=2:
                    stop_reason="repeated_holder_percentage_inconsistency";break
                continue
            if report.get("status")=="diagnostic_sell_quote_rejected":
                quote_rejections+=1
                # Permit a single distinct-candidate continuation, not a retry.
                # An unexplained second HTTP 400 stops this scan.
                if quote_rejections>=2:
                    stop_reason="repeated_sell_quote_http_400";break
                continue
            if report.get("status") not in ("diagnostic_complete","diagnostic_unsupported_mint"):
                stop_reason="diagnostic_failure";break
            if sum(r["diagnostic"].get("status")=="diagnostic_complete" for r in reports)>=limit:break
        except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AttributeError,httpx.HTTPError) as e:
            reports.append({"candidate":row,"diagnostic":{"status":"rejected","reason":str(e) if isinstance(e,PilotError) else type(e).__name__}})
            break
    done=sum(r["diagnostic"].get("status")=="diagnostic_complete" for r in reports)
    skipped=sum(r["diagnostic"].get("status")=="diagnostic_unsupported_mint" for r in reports)
    target_reached=done>=limit
    exhausted=bool(selected) and (target_reached or len(reports)==len(selected)) and done+skipped+quote_rejections+holder_rejections==len(reports)
    status=("scan_no_candidates" if not selected else "scan_partial" if stop_reason or not exhausted or (not target_reached and (done or quote_rejections or holder_rejections)) else
            "scan_no_supported_candidates" if not done else "scan_complete_with_skips" if skipped or quote_rejections or holder_rejections else "scan_complete")
    ref_done=sum(r["candidate"]["mint"] in references and r["diagnostic"].get("status")=="diagnostic_complete" for r in reports)
    return {"status":status,"completed_mints":done,"unsupported_mints":skipped,
            "reference_first":reference_first,"reference_completed_mints":ref_done,
            "temporary_excluded_mints":sorted(excluded),"excluded_mints_found":sorted(excluded_found),
            "nonreference_completed_mints":done-ref_done,
            "reference_mints_discovered":sorted({r["mint"] for r in pools if r["mint"] in references}),
            "reference_mints_missing":sorted(references-{r["mint"] for r in pools}),
            "sell_quote_rejected_mints":quote_rejections,"holder_percentages_rejected_mints":holder_rejections,"stop_reason":stop_reason,
            "retrieved_at":utc().isoformat(),"scope":"geckoterminal_trending_and_top_page_1_plus_dex_search_direct_usdc",
            "target_completed_mints":limit,"target_reached":target_reached,"max_candidates":max_candidates,
            "available_pools":len(pools),"selected_mints":len(selected),"inspected_mints":len(reports),
            "identity_conflicts":conflicts,"identity_conflict_count":len(conflicts),
            "non_target_pools":non_targets,"non_target_pool_count":len(non_targets),
            "eligible_uninspected_candidates":[r for r in eligible if r["mint"] not in {x["candidate"]["mint"] for x in reports}],
            "meme_classification_verified":False,
            "token_identity_verified":False,
            "reports":reports,"security_verified":False,
            "depth_verified":False,"route_integrity_verified":False,"live_data_verified":False,
            "pilot_applied":False,"real_orders":False,"api_key_used":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit",type=int,default=2);p.add_argument("--max-candidates",type=int);p.add_argument("--reference-first",action="store_true");p.add_argument("--exclude-mint",action="append",default=[]);a=p.parse_args()
    try:
        d=run(limit=a.limit,max_candidates=a.max_candidates,reference_first=a.reference_first,exclude_mints=a.exclude_mint)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"] in ("scan_complete","scan_complete_with_skips") else 2 if d["status"] in ("scan_no_candidates","scan_no_supported_candidates") else 1
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AttributeError,httpx.HTTPError) as e:
        print(json.dumps({"status":"rejected","reason":str(e) if isinstance(e,PilotError) else type(e).__name__,"pilot_applied":False,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
