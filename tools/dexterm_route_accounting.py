"""Pure DexTerm route arithmetic and raw quote inspection; no provider requests."""
import re
from cyberbot.solana_pilot import address
from cyberbot.observed_pilot import PilotError
USDC="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

def uint(v,positive=False):
    if not isinstance(v,str) or not re.fullmatch(r"[0-9]{1,20}",v):raise PilotError("Invalid raw quantity")
    n=int(v)
    if n>=2**64 or (positive and n==0):raise PilotError("Raw quantity out of bounds")
    return n

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
    # Provider-declared fields only; no inferred fee accounting.
    fee=raw.get("platformFee")
    bps=raw.get("feeBps")
    summary["reported_fee_bps"]=bps if type(bps) is int and 0<=bps<=10000 else None
    fm=raw.get("feeMint")
    summary["reported_fee_mint"]=fm if address(fm) else None
    fb=fee.get("feeBps") if isinstance(fee,dict) else None
    summary["reported_platform_fee_bps"]=fb if type(fb) is int and 0<=fb<=10000 else None
    if direct:
        summary["direct_input_delta_raw"]=str(sum(int(x["input_raw"]) for x in legs)-amount)
        summary["direct_output_delta_raw"]=str(sum(int(x["output_raw"]) for x in legs)-n)
        summary["direct_bps_sum"]=sum(x["bps"] for x in legs)
    return summary

