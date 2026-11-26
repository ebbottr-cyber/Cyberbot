"""Causal, independent research experiments. No external calls or order access."""
from decimal import Decimal as D
from statistics import median
from datetime import date
from .engine import FEE,SLIP

STRATEGIES={"buy_hold":"Al ve tut","trend":"Hareketli ortalama","momentum":"Momentum","reversion":"Ortalamaya dönüş","cash":"Nakit referansı"}

def signal(name,past,window):
    if name=="cash":return False
    if name=="buy_hold":return True
    avg=sum(past[-window:])/window
    if name=="trend":return past[-1]>avg
    if name=="momentum":return past[-1]>past[-window]
    if name=="reversion":return past[-1]<avg*D(".98")
    raise ValueError("Bilinmeyen strateji.")

def simulate(bars,name,window,start,end):
    cash=D("10000");qty=D(0);cost=D(0);peak=cash;dd=D(0);closed=[];equity=[]
    def sell(price):
        nonlocal cash,qty,cost
        proceeds=qty*price*(1-SLIP)*(1-FEE)
        closed.append(proceeds-cost)
        cash+=proceeds;qty=D(0);cost=D(0)
    for i in range(start,end):
        o,c=bars[i]
        wanted=signal(name,[x[1] for x in bars[i-window:i]],window)
        if wanted and not qty:
            cost=cash
            qty=cash/(o*(1+SLIP)*(1+FEE));cash=D(0)
        elif not wanted and qty:sell(o)
        if i==end-1 and qty:sell(c)
        value=cash+qty*c*(1-SLIP)*(1-FEE)
        equity.append(value);peak=max(peak,value);dd=max(dd,1-value/peak)
    return {"return":cash/D("10000")-1,"drawdown":dd,"closed":len(closed),"wins":sum(p>0 for p in closed),"equity":equity}

def comparison(raw,*,mode,symbol):
    if mode not in ("synthetic","historical_unverified"):raise ValueError("Geçersiz veri modu.")
    if not 60<=len(raw)<=6000:raise ValueError("En az 60, en fazla 6000 gözlem gerekli.")
    bars=[]
    previous=None
    for row in raw:
        o,c=(D(str(row[k])) for k in ("open","close"))
        if any(not v.is_finite() or not D("0.000000000001")<=v<=D("1000000000") for v in (o,c)):raise ValueError("Geçersiz fiyat.")
        if mode=="historical_unverified":
            session=date.fromisoformat(row["session"])
            if previous is not None and session<=previous:raise ValueError("Tarih sırası geçersiz.")
            previous=session
        bars.append((o,c))
    split=len(bars)*7//10
    windows=(3,5,10)
    pct=lambda v:str((v*100).quantize(D(".01")))
    results=[]
    for name,label in STRATEGIES.items():
        # Select only on training; holdout is never used for parameter selection.
        chosen=max(windows,key=lambda w:simulate(bars,name,w,10,split)["return"]) if name not in ("cash","buy_hold") else 3
        train=simulate(bars,name,chosen,10,split)
        test=simulate(bars,name,chosen,split,len(bars))
        results.append({"id":name,"name":label,"window":chosen,"training_return_pct":pct(train["return"]),
                        "holdout_return_pct":pct(test["return"]),"holdout_drawdown_pct":pct(test["drawdown"]),
                        "closed":test["closed"],"win_pct":pct(D(test["wins"])/test["closed"]) if test["closed"] else None})
    return {"mode":mode,"symbol":symbol,"observations":len(bars),"training_observations":split-10,
            "holdout_observations":len(bars)-split,"fee_bps":str(FEE*10000),"slippage_bps":str(SLIP*10000),
            "strategies":results,"real_orders":False,"promotion_enabled":False,
            "limitations":["Tek zaman ayrımı; tekrar eden holdout kullanımı seçim yanlılığı yaratabilir.","Tek varlık, uzun pozisyon; tam sermaye tahsisi araştırma varsayımıdır.","Seans ve kurumsal işlem doğrulaması yok; fiyat etkisi ve likidite modellenmez."]}

def synthetic():
    # Deterministic synthetic scenarios, not a reconstructed market.
    rows=[]
    prior=D(100)
    for i in range(180):
        change=D(((i*17)%19)-9)/1000 + (D(".002") if i<90 else D("-.001"))
        close=prior*(1+change)
        rows.append({"open":str(prior),"close":str(close)})
        prior=close
    return comparison(rows,mode="synthetic",symbol="DEMO-LAB")
