"""Review a saved DexTerm report offline; never authorize a trade."""
import argparse
import json
import math
import time
from pathlib import Path
from cyberbot.solana_pilot import address
from decimal import Decimal

# DexTerm review policy; no legacy pool discovery/provider import.
LIMIT = Decimal("100000")
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

MAX_BYTES = 2 * 1024 * 1024
WRAPPED_SOL = "So11111111111111111111111111111111111111112"

def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)

def review(report, *, now_ms=None):
    if not isinstance(report, dict) or report.get("source") != "dexterm_screener_query":
        raise ValueError("Invalid report source")
    if report.get("status") != "diagnostic_complete" or report.get("source_error_count") != 0:
        raise ValueError("Incomplete source report")
    for key in ("security_verified", "live_data_verified", "pilot_applied", "real_orders"):
        if report.get(key) is not False:
            raise ValueError("Unexpected report verification flags")
    rows = report.get("candidates")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10 or report.get("candidate_count") != len(rows):
        raise ValueError("Invalid report candidate count")
    now_ms = int(time.time()*1000) if now_ms is None else now_ms
    seen=set()
    results=[]
    for row in rows:
        if not isinstance(row,dict) or not address(row.get("mint")) or row["mint"] in seen:
            raise ValueError("Invalid or duplicate candidate")
        mint=row["mint"];seen.add(mint)
        v=row.get("reported")
        if not isinstance(v,dict):
            raise ValueError("Invalid reported fields")
        price,liq,ts,age=(v.get(k) for k in ("priceUsd","liquidityUsd","fetchedAt","ageSec"))
        reasons=[]
        if mint in (USDC,WRAPPED_SOL):reasons.append("non_target_asset")
        if not numeric(price) or not 0<price<=1e12:reasons.append("missing_or_invalid_price")
        if not numeric(liq) or not float(LIMIT)<=liq<=1e12:reasons.append("reported_liquidity_below_limit_or_invalid")
        if not numeric(age) or not 0<=age<=30:reasons.append("reported_age_missing_or_over_30s")
        if not numeric(ts) or not 0<ts<=now_ms:reasons.append("missing_or_invalid_source_timestamp")
        elapsed=round((now_ms-ts)/1000,3) if numeric(ts) and 0<ts<=now_ms else None
        results.append({"mint":mint,"reported_liquidity_usd":liq if numeric(liq) else None,
                        "reported_age_at_scan_seconds":age if numeric(age) else None,
                        "age_at_review_seconds":elapsed,
                        "fresh_at_review":elapsed is not None and elapsed<=30,
                        "review_status":"excluded" if reasons else "historical_candidate_for_pool_lookup",
                        "reasons":reasons,"security_verified":False,"trade_eligible":False})
    shortlist=[r["mint"] for r in results if not r["reasons"]]
    return {"status":"offline_review_complete","candidate_count":len(results),
            "shortlist_count":len(shortlist),"shortlist_mints":shortlist,"candidates":results,
            "research_liquidity_floor_usd":int(LIMIT),"research_age_limit_seconds":30,
            "pool_identity_verified":False,"meme_classification_verified":False,
            "security_verified":False,"depth_verified":False,"live_data_verified":False,
            "pilot_applied":False,"real_orders":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report",required=True)
    a=p.parse_args()
    try:
        with Path(a.report).open("rb") as f:
            data=f.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError("Report exceeds size limit")
        print(json.dumps(review(json.loads(data.decode("utf-8-sig"))),indent=2,allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, ArithmeticError, OSError) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,"real_orders":False,"pilot_applied":False}))
        return 1
if __name__=="__main__":raise SystemExit(main())
