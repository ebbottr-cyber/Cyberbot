"""Offline Token-2022 extension policy triage; no safety clearance or execution."""
import argparse,json
from pathlib import Path
from cyberbot.solana_pilot import address
from tools.solana_token2022_research import TOKEN2022,EXTENSIONS
from tools.dexterm_pool_bridge import FLAGS
from tools.dexterm_research_archive import MAX_BYTES

METADATA={"metadataPointer","tokenMetadata"}
TRANSFER_CONTROL={"transferHook","permanentDelegate","defaultAccountState",
                  "nonTransferable","pausableConfig","pausable"}
FEE_OR_ACCOUNTING={"transferFeeConfig","confidentialTransferMint",
                   "confidentialTransferFeeConfig","confidentialMintBurn",
                   "interestBearingConfig","scaledUiAmountConfig"}
RISK_FIELDS=("security_verified","extensions_verified","trade_eligible")

def review_row(row):
    if not isinstance(row,dict) or not address(row.get("mint")):
        raise ValueError("Invalid observed mint")
    if row.get("status")!="token2022_observed":
        return {"mint":row["mint"],"classification":"not_token2022_observed",
                "reasons":["no_token2022_observation"],"trade_eligible":False}
    if row.get("program_owner")!=TOKEN2022 or any(row.get(k) is not False for k in ("extensions_verified","trade_eligible")):
        raise ValueError("Invalid observation flags")
    names=row.get("reported_extensions")
    if not isinstance(names,list) or len(names)>64 or any(not isinstance(n,str) or n not in EXTENSIONS for n in names) or len(set(names))!=len(names):
        raise ValueError("Invalid extension names")
    unknown=row.get("unknown_extension_count")
    reasons=[]
    for key in ("mint_authority","freeze_authority"):
        if row.get(key) not in ("disabled","present","not_reported"):
            raise ValueError("Invalid authority state")
        if row[key]!="disabled":reasons.append(key+"_not_confirmed_disabled")
    reported=row.get("extension_list_reported")
    if type(reported) is not bool:raise ValueError("Invalid extension reporting flag")
    if reported and (type(unknown) is not int or not 0<=unknown<=64 or len(names)+unknown>64):
        raise ValueError("Invalid unknown extension count")
    if not reported and (names or unknown is not None):
        raise ValueError("Inconsistent missing extension list")
    if not reported:reasons.append("extension_list_missing")
    if unknown:reasons.append("unknown_extensions_present")
    controls=sorted(set(names)&TRANSFER_CONTROL)
    accounting=sorted(set(names)&FEE_OR_ACCOUNTING)
    other=sorted(set(names)-METADATA-TRANSFER_CONTROL-FEE_OR_ACCOUNTING)
    reasons+=["transfer_control:"+n for n in controls]
    reasons+=["fee_or_accounting:"+n for n in accounting]
    reasons+=["other_extension:"+n for n in other]
    category="additional_controls_require_review" if reasons else "metadata_or_empty_list_observed"
    return {"mint":row["mint"],"classification":category,"reported_extensions":names,
            "reasons":reasons,"extension_state_verified":False,
            "security_verified":False,"trade_eligible":False}

def review(report):
    if not isinstance(report,dict) or report.get("status")!="research_complete" or report.get("research_only") is not True:
        raise ValueError("Complete research report required")
    if any(report.get(k) is not False for k in ("extensions_verified","security_verified","live_data_verified","pilot_applied","real_orders")):
        raise ValueError("Unexpected research flags")
    rows=report.get("observations")
    if not isinstance(rows,list) or not 1<=len(rows)<=3 or len(rows)!=report.get("selected_mints"):
        raise ValueError("Invalid observation count")
    results=[review_row(r) for r in rows]
    if len({r["mint"] for r in results})!=len(results):raise ValueError("Duplicate mint")
    if report.get("token2022_count")!=sum(r["status"]=="token2022_observed" for r in rows):
        raise ValueError("Invalid Token-2022 count")
    return {"status":"token2022_risk_review_complete","research_only":True,
            "source_retrieved_at":report.get("retrieved_at"),"observations":results,
            "review_count":len(results),"additional_controls_count":sum(r["classification"]=="additional_controls_require_review" for r in results),
            "metadata_or_empty_count":sum(r["classification"]=="metadata_or_empty_list_observed" for r in results),
            "extensions_verified":False,"trade_eligible":False,"network_requests":False,**FLAGS}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report",required=True)
    args=p.parse_args()
    try:
        with Path(args.report).open("rb") as f:data=f.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError("Oversized report")
        print(json.dumps(review(json.loads(data.decode("utf-8-sig"))),indent=2,allow_nan=False))
        return 0
    except (ValueError,TypeError,KeyError,AttributeError,OSError,ArithmeticError) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,**FLAGS}))
        return 1
if __name__=="__main__":raise SystemExit(main())
