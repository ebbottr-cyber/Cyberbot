"""Causal instrument regime research; labels known before the next opening."""
from collections import Counter
from datetime import date
from decimal import Decimal as D
from statistics import pstdev
from .capital import CAPITAL
from .strategy_lab import STRATEGIES,simulate
from .learning import WINDOWS,TRAIN,TEST
from .robustness import returns_from,metrics

LOOKBACK=20
TREND_THRESHOLD=.03
VOL_THRESHOLD=.025
MIN_OBSERVATIONS=40
REGIMES={"bull":"Yükseliş","bear":"Düşüş","sideways":"Yatay","volatile":"Yüksek volatilite"}

def classify(closes):
    if len(closes)<LOOKBACK+1:raise ValueError("En az 21 kapanış gerekli.")
    p=[float(x) for x in closes[-(LOOKBACK+1):]]
    import math
    if any(not math.isfinite(x) or x<=0 for x in p):raise ValueError("Geçersiz kapanış.")
    returns=[b/a-1 for a,b in zip(p,p[1:])]
    vol=pstdev(returns);trend=p[-1]/p[0]-1
    label="volatile" if vol>=VOL_THRESHOLD else "bull" if trend>=TREND_THRESHOLD else "bear" if trend<=-TREND_THRESHOLD else "sideways"
    return {"id":label,"label":REGIMES[label],"trend_pct":round(trend*100,4),"volatility_pct":round(vol*100,4)}

def demo_rows(market):
    # Different deterministic phases and amplitude per market, not real data.
    if market not in CAPITAL:raise ValueError("Geçersiz piyasa.")
    j=list(CAPITAL).index(market)
    p=D(100);rows=[]
    for i in range(360):
        phase=(i//90)%4
        shift=(D(".006"),D("-.006"),D(0),D(0))[phase]
        wave=D(((i*7+j*3)%11)-5)*(D(".012") if phase==3 else D(".0007"))
        c=p*(1+shift+wave)
        rows.append({"open":str(p),"close":str(c)})
        p=c
    return rows

def evaluate(raw,*,mode,market,symbol):
    if market not in CAPITAL or mode not in ("synthetic","historical_unverified"):
        raise ValueError("Geçersiz piyasa veya veri modu.")
    if not 120<=len(raw)<=1000:raise ValueError("120–1000 gözlem gerekli.")
    bars=[];prev=None
    for row in raw:
        o,c=(D(str(row[k])) for k in ("open","close"))
        if any(not x.is_finite() or not D("1e-12")<=x<=D("1e9") for x in (o,c)):raise ValueError("Geçersiz fiyat.")
        if mode=="historical_unverified":
            session=date.fromisoformat(row["session"])
            if prev is not None and session<=prev:raise ValueError("Tarih sırası geçersiz.")
            prev=session
        bars.append((o,c))
    closes=[x[1] for x in bars]
    # A label at index i only uses closes through i-1. Never classify using the outcome bar.
    labels={i:classify(closes[i-LOOKBACK-1:i])["id"] for i in range(TRAIN,len(bars))}
    tested=list(range(TRAIN,TRAIN+((len(bars)-TRAIN)//TEST)*TEST))
    counts=Counter(labels[i] for i in tested)
    strategies=[]
    for name,title in STRATEGIES.items():
        grouped={reg:[] for reg in REGIMES}
        for start in range(TRAIN,len(bars)-TEST+1,TEST):
            window=max(WINDOWS,key=lambda w:simulate(bars,name,w,start-TRAIN+20,start)["return"]) if name not in ("cash","buy_hold") else 3
            result=simulate(bars,name,window,start,start+TEST)
            for i,ret in enumerate(returns_from(result),start):
                grouped[labels[i]].append(ret)
        for reg,rets in grouped.items():
            n=len(rets)
            # Conditional observations need not be contiguous. Arithmetic mean, not a fabricated portfolio curve.
            strategies.append({"strategy":name,"name":title,"regime":reg,"observations":n,
                "mean_net_return_pct":round(sum(rets)/n*100,5) if n else None,
                "positive_observation_pct":round(sum(x>0 for x in rets)/n*100,2) if n else None,
                "status":"descriptive_only" if n>=MIN_OBSERVATIONS else "insufficient_sample"})
    currency,capital=CAPITAL[market]
    return {"version":"regime-1","mode":mode,"market":market,"symbol":symbol,"currency":currency,"initial_capital":str(capital),
        "observations":len(bars),"tested_observations":len(tested),"next_observation_regime":classify(closes),
        "regime_counts":{k:counts[k] for k in REGIMES},"strategies":strategies,
        "thresholds":{"lookback_returns":LOOKBACK,"trend_pct":TREND_THRESHOLD*100,"volatility_per_observation_pct":VOL_THRESHOLD*100,"minimum_regime_observations":MIN_OBSERVATIONS},
        "real_orders":False,"promotion_enabled":False,"profitability_verified":False,"automatic_strategy_switching":False,
        "limits":["Tek sembol rejimi; tüm borsanın rejimi değildir.",
        "20 gözlemlik kapanış getirisi ve standart sapma; volatilite öncelikli, yıllıklandırılmaz. Sabit deneysel eşikler.",
        "Etiket bir önceki kapanışta belirlenir. Açık pozisyonların net özsermaye değişimi, o gözlemin rejimine yazılır.",
        "Rejim gözlemleri bitişik olmayabilir; ortalama getiri bir portföy getirisi veya strateji seçim kuralı değildir.",
        "40 gözlem altı yetersiz örneklem. Sentetik ve doğrulanmamış arşiv gerçek kârlılık kanıtı değildir."]}
