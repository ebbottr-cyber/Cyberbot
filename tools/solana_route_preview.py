"""Anonymous quote route preview. Never writes pilot state or submits transactions."""
import argparse,json,os
from decimal import Decimal as D
import httpx
from cyberbot.solana_pilot import address
from cyberbot.providers.solana_observed import request,uint,USDC,AMOUNT,PilotError
from cyberbot.observed_pilot import utc

def accounting(legs,inp,out,amount,reported):
    # Check arithmetic on reported legs, not execution, fees, or on-chain state.
    incoming={};outgoing={};edges={}
    for x in legs:
        a,b=x["input_mint"],x["output_mint"]
        outgoing[a]=outgoing.get(a,0)+int(x["input_raw"])
        incoming[b]=incoming.get(b,0)+int(x["output_raw"])
        edges.setdefault(a,set()).add(b)
    nodes=set(incoming)|set(outgoing)
    def visit(start,graph):
        seen=set();todo=[start]
        while todo:
            n=todo.pop()
            if n in seen:continue
            seen.add(n);todo.extend(graph.get(n,()))
        return seen
    reverse={}
    for a,bs in edges.items():
        for b in bs:reverse.setdefault(b,set()).add(a)
    cyclic=any(a in visit(b,edges) for a,bs in edges.items() for b in bs)
    internal={m:str(incoming.get(m,0)-outgoing.get(m,0)) for m in sorted(nodes-{inp,out})}
    input_delta=outgoing.get(inp,0)-amount
    output_delta=incoming.get(out,0)-reported
    bps=sum(x["bps"] for x in legs if x["input_mint"]==inp)
    graph_ok=(not cyclic and inp not in incoming and out not in outgoing
              and nodes<=visit(inp,edges) and nodes<=visit(out,reverse))
    return {"input_delta_raw":str(input_delta),"intermediate_net_raw":internal,
            "terminal_gross_minus_reported_raw":str(output_delta),"source_bps_sum":bps,
            "graph_connected_acyclic":graph_ok,
            "reported_input_and_intermediate_balanced":graph_ok and input_delta==0 and all(v=="0" for v in internal.values()),
            "terminal_output_exact_match":output_delta==0,
            "fee_semantics_verified":False}

def inspect(raw,inp,out,amount):
    if not isinstance(raw,dict) or raw.get("error") or raw.get("errorCode") not in (None,0):
        raise PilotError("Quote unavailable")
    if raw.get("transaction") not in (None,"") or raw.get("taker") not in (None,""):
        raise PilotError("Wallet-free quote required")
    if (raw.get("inputMint"),raw.get("outputMint"),raw.get("swapMode"))!=(inp,out,"ExactIn") or uint(raw.get("inAmount"),True)!=amount:
        raise PilotError("Quote identity or amount mismatch")
    n=uint(raw.get("outAmount"),True)
    routes=raw.get("routePlan")
    if not isinstance(routes,list) or not 1<=len(routes)<=32:
        raise PilotError("Missing or oversized route plan")
    legs=[]
    for route in routes:
        s=route["swapInfo"]
        pool,a,b=(s.get(k) for k in ("ammKey","inputMint","outputMint"))
        if not all(address(x) for x in (pool,a,b)) or a==b:
            raise PilotError("Invalid route leg identity")
        u,v=uint(s.get("inAmount"),True),uint(s.get("outAmount"),True)
        bps=route.get("bps")
        if type(bps) is not int or not 1<=bps<=10000:
            raise PilotError("Invalid route allocation")
        legs.append({"pool":pool,"input_mint":a,"output_mint":b,
                     "input_raw":str(u),"output_raw":str(v),"bps":bps})
    direct=all(x["input_mint"]==inp and x["output_mint"]==out for x in legs)
    summary={"reported_input_raw":str(amount),"reported_output_raw":str(n),
             "route_kind":("single_direct" if len(legs)==1 else "split_direct") if direct else "multi_hop_or_mixed",
             "legs":legs,"route_integrity_verified":False,
             "accounting":accounting(legs,inp,out,amount,n)}
    if direct:
        summary["direct_input_delta_raw"]=str(sum(int(x["input_raw"]) for x in legs)-amount)
        summary["direct_output_delta_raw"]=str(sum(int(x["output_raw"]) for x in legs)-n)
        summary["direct_bps_sum"]=sum(x["bps"] for x in legs)
    return summary

def run(mint,*,transport=None,clock=utc):
    if os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise PilotError("Explicit data usage permission required")
    if not address(mint) or mint==USDC:
        raise PilotError("Invalid base mint")
    started=clock()
    with httpx.Client(timeout=httpx.Timeout(8,connect=6),follow_redirects=False,trust_env=False) as c:
        def get(a,b,n):
            params={"inputMint":a,"outputMint":b,"amount":str(n)}
            raw=transport(params) if transport else request(c,"quote",params,"")
            return inspect(raw,a,b,n)
        buy=get(USDC,mint,AMOUNT)
        sell=get(mint,USDC,int(buy["reported_output_raw"]))
    if not 0<=(clock()-started).total_seconds()<=30:
        raise PilotError("Preview time budget exceeded")
    return {"status":"route_preview_only","mint":mint,"retrieved_at":clock().isoformat(),
            "buy":buy,"sell":sell,
            "reported_roundtrip_return_usdc":str(D(sell["reported_output_raw"])/D(10**6)),
            "reported_roundtrip_pct":str((D(sell["reported_output_raw"])/D(AMOUNT)-1)*100),
            "quote_source_timestamp_verified":False,"route_integrity_verified":False,
            "security_verified":False,"depth_verified":False,"usd_conversion_verified":False,
            "live_data_verified":False,"pilot_applied":False,"real_orders":False,
            "api_key_used":False,"transport_mocked":transport is not None}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mint",required=True)
    args=p.parse_args()
    try:
        print(json.dumps(run(args.mint),indent=2));return 0
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AttributeError) as e:
        print(json.dumps({"status":"rejected","reason":str(e) if isinstance(e,PilotError) else "Invalid preview response","pilot_applied":False,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
