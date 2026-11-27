"""One-shot read-only public Solana diagnostics. No ledger writes or entry authorization."""
import argparse,json,os
from decimal import Decimal as D
import httpx
from cyberbot.solana_pilot import address
from cyberbot.providers.solana_observed import request,mint_info,reported_holders,pool_info,USDC,PilotError,RPC_ENDPOINTS,UnsupportedMint,SellQuoteRejected
from cyberbot.observed_pilot import utc,ts
from tools.solana_route_preview import run as preview

def run(mint,pool):
    if os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise PilotError("Explicit data usage permission required")
    if not address(mint) or not address(pool) or mint in (pool,USDC):
        raise PilotError("Invalid mint or pool")
    stages={}
    def stage(name,fn):
        try:stages[name]={"status":"ok","data":fn()}
        except SellQuoteRejected as e:
            stages[name]={"status":"quote_rejected","reason":str(e)}
        except UnsupportedMint as e:
            stages[name]={"status":"unsupported","reason":str(e)}
        except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AttributeError,httpx.HTTPError) as e:
            stages[name]={"status":"rejected","reason":str(e) if isinstance(e,PilotError) else type(e).__name__}
    def finish(status):
        return {"status":status,"mint":mint,"reference_pool":pool,"retrieved_at":utc().isoformat(),"stages":stages,
                "reference_pool_is_execution_route":False,"security_verified":False,"depth_verified":False,
                "route_integrity_verified":False,"live_data_verified":False,"pilot_applied":False,
                "real_orders":False,"api_key_used":False}
    with httpx.Client(timeout=httpx.Timeout(8,connect=6),follow_redirects=False,trust_env=False) as c:
        stage("mint",lambda:mint_info(request(c,"rpc",("getAccountInfo",[mint,{"encoding":"jsonParsed","commitment":"finalized"}]),"",rpc_url=RPC_ENDPOINTS["rpcnode"])))
        if stages["mint"]["status"]!="ok":
            return finish("diagnostic_unsupported_mint" if stages["mint"]["status"]=="unsupported" else "diagnostic_partial")
        def holders():
            x=reported_holders(request(c,"rugcheck",mint,""),request(c,"gecko_holders",mint,""),mint)
            age=(utc()-ts(x["geckoterminal_holder_source_at"])).total_seconds()
            x["geckoterminal_report_age_seconds"]=age
            x["reported_concentration_over_pilot_limit"]=max(D(x["rugcheck_reported_top10_account_pct"]),D(x["geckoterminal_reported_top10_pct"]))>30
            return x
        stage("holders",holders)
        if stages["holders"]["status"]!="ok":return finish("diagnostic_partial")
        stage("reference_pool",lambda:pool_info(request(c,"pool",pool,""),mint,pool))
        if stages["reference_pool"]["status"]!="ok":return finish("diagnostic_partial")
    stage("route_preview",lambda:preview(mint))
    if stages["route_preview"]["status"]=="quote_rejected":
        return finish("diagnostic_sell_quote_rejected")
    return finish("diagnostic_complete" if all(s["status"]=="ok" for s in stages.values()) else "diagnostic_partial")
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mint",required=True);p.add_argument("--pool",required=True)
    args=p.parse_args()
    try:
        result=run(args.mint,args.pool);print(json.dumps(result,indent=2))
        return 0 if result["status"]=="diagnostic_complete" else 1
    except PilotError as e:
        print(json.dumps({"status":"rejected","reason":str(e),"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
