"""Inspect previously unsupported mints, without altering legacy pilot eligibility."""
import argparse,json,os,sqlite3,time
from pathlib import Path
import httpx
from cyberbot.solana_pilot import address
from cyberbot.providers.solana_observed import request,rpc_result,uint,LEGACY,RPC_ENDPOINTS,PilotError
from cyberbot.observed_pilot import utc
from tools.dexterm_research_archive import APP_ID
from tools.dexterm_pool_bridge import FLAGS
from tools.solana_token2022_extension_state import observe

TOKEN2022="TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
EXTENSIONS={"transferFeeConfig","mintCloseAuthority","confidentialTransferMint",
            "defaultAccountState","nonTransferable","interestBearingConfig",
            "permanentDelegate","transferHook","confidentialTransferFeeConfig",
            "metadataPointer","tokenMetadata","groupPointer","tokenGroup",
            "groupMemberPointer","tokenGroupMember","scaledUiAmountConfig",
            "pausableConfig","pausable","confidentialMintBurn"}

def authority(info,key):
    if key not in info:return "not_reported"
    if info[key] is None:return "disabled"
    if address(info[key]):return "present"
    raise ValueError("Invalid authority")

def classify(raw,*,mint=None):
    slot,v=rpc_result(raw)
    if not isinstance(v,dict) or not address(v.get("owner")) or type(v.get("executable")) is not bool:
        raise ValueError("Invalid account")
    owner=v["owner"]
    d={"slot":slot,"program_owner":owner,"extensions_verified":False,"trade_eligible":False}
    if owner not in (TOKEN2022,LEGACY):
        return dict(d,status="other_program")
    if v["executable"]:return dict(d,status="not_mint")
    data=v.get("data")
    if not isinstance(data,dict) or data.get("program")!=("spl-token-2022" if owner==TOKEN2022 else "spl-token"):
        raise ValueError("Missing or mismatched parsed token data")
    parsed=data.get("parsed")
    if not isinstance(parsed,dict) or not isinstance(parsed.get("type"),str):
        raise ValueError("Invalid parsed account")
    if parsed["type"]!="mint":return dict(d,status="not_mint")
    info=parsed["info"]
    if not isinstance(info,dict) or info.get("isInitialized") is not True or type(info.get("decimals")) is not int or not 0<=info["decimals"]<=255:
        raise ValueError("Invalid mint")
    d.update(decimals=info["decimals"],supply_raw=str(uint(info["supply"])),
             mint_authority=authority(info,"mintAuthority"),freeze_authority=authority(info,"freezeAuthority"))
    if owner==LEGACY:return dict(d,status="legacy_mint_observed")
    ext=info.get("extensions")
    if ext is None:
        return dict(d,status="token2022_observed",extension_list_reported=False,reported_extensions=[],unknown_extension_count=None)
    if not isinstance(ext,list) or len(ext)>64:raise ValueError("Invalid extension list")
    names=[];details=[];unknown=0
    for x in ext:
        if not isinstance(x,dict) or not isinstance(x.get("extension"),str):
            raise ValueError("Invalid extension entry")
        name=x["extension"]
        if name in EXTENSIONS:
            if name in names:raise ValueError("Duplicate extension")
            names.append(name)
            details.append(observe(x,mint))
        else:unknown+=1
    return dict(d,status="token2022_observed",extension_list_reported=True,
                reported_extensions=sorted(names),unknown_extension_count=unknown,
                extension_state_observations=sorted(details,key=lambda x:x["extension"]),
                extension_state_verified=False)

def archived_mints(database,limit):
    if type(limit) is not int or not 1<=limit<=3:raise ValueError("Limit 1 to 3")
    path=Path(database).resolve(strict=True)
    con=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=10)
    try:
        if con.execute("PRAGMA application_id").fetchone()[0]!=APP_ID or con.execute("PRAGMA user_version").fetchone()[0]!=1:
            raise ValueError("Wrong research archive")
        rows=con.execute("""SELECT o.mint FROM research_observations o
          JOIN research_reports r ON r.digest=o.digest
          WHERE o.kind='snapshot' AND o.status='diagnostic_unsupported_mint'
          GROUP BY o.mint ORDER BY (SELECT COUNT(*) FROM research_observations seen WHERE seen.mint=o.mint AND seen.kind='token2022'),MAX(r.imported_utc) DESC,o.mint LIMIT ?""",(limit,)).fetchall()
        mints=[r[0] for r in rows]
        if any(not address(m) for m in mints):raise ValueError("Invalid archived mint")
        return mints
    finally:con.close()

def run(database,*,limit=3,request_fn=request,sleep=time.sleep):
    if os.getenv("CYBERBOT_PILOT_KILL_SWITCH")!="1" or os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise PilotError("Research permissions required")
    mints=archived_mints(database,limit)
    out={"status":"research_complete" if mints else "no_archived_candidates",
         "selected_mints":len(mints),"observations":[],"retrieved_at":utc().isoformat(),
         "research_only":True,"extensions_verified":False,"api_key_used":False,**FLAGS}
    with httpx.Client(timeout=httpx.Timeout(8,connect=6),follow_redirects=False,trust_env=False) as c:
        for i,mint in enumerate(mints):
            if i:sleep(3)
            try:
                raw=request_fn(c,"rpc",("getAccountInfo",[mint,{"encoding":"jsonParsed","commitment":"finalized"}]),"",rpc_url=RPC_ENDPOINTS["rpcnode"])
                out["observations"].append({"mint":mint,**classify(raw,mint=mint)})
            except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AttributeError,httpx.HTTPError) as e:
                out["observations"].append({"mint":mint,"status":"rejected","reason":str(e) if isinstance(e,PilotError) else type(e).__name__})
                out["status"]="research_partial"
                break
    out["token2022_count"]=sum(r["status"]=="token2022_observed" for r in out["observations"])
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--limit",type=int,default=3)
    a=p.parse_args()
    try:
        d=run(a.database,limit=a.limit)
        print(json.dumps(d,indent=2,allow_nan=False))
        return 0 if d["status"]=="research_complete" else 2 if d["status"]=="no_archived_candidates" else 1
    except (ValueError,TypeError,KeyError,AttributeError,OSError,ArithmeticError,sqlite3.Error,httpx.HTTPError) as e:
        print(json.dumps({"status":"rejected","error_type":type(e).__name__,**FLAGS}))
        return 1
if __name__=="__main__":raise SystemExit(main())
