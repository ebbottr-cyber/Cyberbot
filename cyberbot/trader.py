"""Independent cost-aware shadow research. Input is explicitly synthetic or unverified manual evidence."""
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from collections import defaultdict

D=Decimal
class ResearchError(ValueError): pass

def number(value,low,high):
    try:
        if not isinstance(value,str) or len(value)>48: raise ValueError()
        n=D(value)
        if not n.is_finite() or not low<=n<=high: raise ValueError()
        return n
    except (ValueError,InvalidOperation):
        raise ResearchError("Sayısal kanıt geçersiz.") from None

def stamp(value):
    try:
        if not isinstance(value,str): raise ValueError()
        t=datetime.fromisoformat(value.replace("Z","+00:00"))
        if t.utcoffset() is None or t>datetime.now(timezone.utc): raise ValueError()
        return t
    except (ValueError,OverflowError):
        raise ResearchError("Zaman damgası geçersiz.") from None

def evaluate(records):
    if not isinstance(records,list) or not 1<=len(records)<=5000:
        raise ResearchError("1–5000 kapanmış gölge gözlemi gerekli.")
    results=defaultdict(list)
    seen=set()
    for row in records:
        if not isinstance(row,dict): raise ResearchError("Gözlem geçersiz.")
        wallet=row.get("wallet")
        event=row.get("event")
        if not isinstance(wallet,str) or not wallet or len(wallet)>64 or not isinstance(event,str) or not event or len(event)>128 or (wallet,event) in seen:
            raise ResearchError("Eksik veya tekrar eden gözlem.")
        seen.add((wallet,event))
        signal,entry,exit=(stamp(row.get(k)) for k in ("signal_at","entry_at","exit_at"))
        if not signal<entry<exit: raise ResearchError("Sinyal, giriş ve çıkış sırası geçersiz.")
        p0=number(row.get("entry_price"),D("0.000000000001"),D("1000000000"))
        p1=number(row.get("exit_price"),D("0.000000000001"),D("1000000000"))
        fee=number(row.get("fee_bps"),D(0),D(1000))/10000
        slip=number(row.get("slippage_bps"),D(0),D(3000))/10000
        net=p1*(1-slip)*(1-fee)/(p0*(1+slip)*(1+fee))-1
        results[wallet].append((exit,net))
    output=[]
    for wallet,values in results.items():
        values.sort(key=lambda x:x[0])
        xs=[x[1] for x in values]; n=len(xs)
        # Small samples shrink towards zero; one exceptional win does not establish skill.
        mean=sum(xs,D(0))/n
        shrunk=sum(xs,D(0))/(n+10)
        ex_best=(sum(xs,D(0))-max(xs))/(n-1) if n>1 else None
        win=D(sum(x>0 for x in xs))/n
        status="yetersiz_ornek" if n<20 else "arastirma_adayi" if shrunk>0 and ex_best is not None and ex_best>0 else "zayif_kanit"
        pct=lambda x: str((x*100).quantize(D(".01"))) if x is not None else None
        output.append({"wallet":wallet,"closed_samples":n,"win_pct":pct(win),"mean_net_pct":pct(mean),"adjusted_mean_pct":pct(shrunk),"excluding_best_pct":pct(ex_best),"status":status})
    return sorted(output,key=lambda x:(x["closed_samples"]>=20,D(x["adjusted_mean_pct"])),reverse=True)

def demo():
    records=[]
    for name,prices in [("DEMO-A",[("1","1.02"),("1","0.99"),("1","1.04")]),("DEMO-B",[("1","1.3"),("1","0.94"),("1","0.95")])]:
        for i,(a,b) in enumerate(prices):
            records.append({"wallet":name,"event":str(i),"signal_at":"2020-01-01T00:00:00Z","entry_at":"2020-01-01T00:01:00Z","exit_at":"2020-01-01T00:02:00Z","entry_price":a,"exit_price":b,"fee_bps":"30","slippage_bps":"75"})
    return evaluate(records)
