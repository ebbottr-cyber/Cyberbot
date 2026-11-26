"""Causal Futures shadow replay with regime gating and liquidation quarantine."""
from collections import Counter
from decimal import Decimal as D
from .adaptive import decide,CANDIDATES
from .strategy_memory import initial,update,filter_choice
from .futures_research import simulate,WINDOWS,BLOCK,NAMES
from .futures import START
from .regimes import classify
from .robustness import metrics

def evaluate(bars):
    if not 240<=len(bars)<=1000:raise ValueError("240–1000 sentetik gözlem gerekli.")
    if any(not x.is_finite() or not D("1e-12")<=x<=D("1e9") for b in bars for x in b):raise ValueError("Geçersiz fiyat.")
    closes=[b[1] for b in bars]
    evidence={n:[] for n in CANDIDATES}
    states={n:initial() for n in CANDIDATES}
    shadow=[];stress=[];decisions=[];blocks=[]
    for start in range(60,len(bars)-BLOCK+1,BLOCK):
        end=start+BLOCK
        regime=classify(closes[:start])["id"]
        # All evidence used here was completed before this block.
        choice=filter_choice(decide(regime,evidence),states)
        selected=choice["strategy"]
        windows={n:max(WINDOWS,key=lambda w:simulate(bars,n,w,start-40,start)["net"]) for n in CANDIDATES}
        results={n:(simulate(bars,n,w,start,end),simulate(bars,n,w,start,end,2)) for n,w in windows.items()}
        if selected=="cash":
            a=b=simulate(bars,"cash",5,start,end)
        else:a,b=results[selected]
        shadow.extend(a["returns"]);stress.extend(b["returns"])
        decisions.append({"start":start,"end_exclusive":end,"regime":regime,"selected":selected,
                          "window":windows.get(selected),"evidence_folds":len(evidence[CANDIDATES[0]]),
                          "ranking":choice["ranking"],"return_pct":round(a["net"]*100,5),
                          "closed_trades":a["closed"],"liquidations":a["liquidations"]})
        # Outcomes become evidence only after the block has ended.
        for n,(base,costly) in results.items():
            evidence[n].append({"closed":base["closed"],"observations":[(regime,x,y) for x,y in zip(base["returns"],costly["returns"])]})
            block={"strategy":n,"regime":regime,"start_key":f"{start:06d}","end_key":f"{end-1:06d}",
                   "return_pct":base["net"]*100,"double_cost_return_pct":costly["net"]*100,
                   "drawdown_pct":base["dd"]*100,"double_cost_drawdown_pct":costly["dd"]*100,
                   "closed_trades":base["closed"],"liquidations":base["liquidations"]+costly["liquidations"]}
            blocks.append(block);states[n]=update(states[n],block)
    next_regime=classify(closes)
    choice=filter_choice(decide(next_regime["id"],evidence),states)
    def summary(values):
        net,dd=metrics(values)
        return {"return_pct":round(net*100,5),"drawdown_pct":round(dd*100,5),
                "ending_capital":str((START*(1+D(str(net)))).quantize(D(".01")))}
    counts=Counter(d["selected"] for d in decisions)
    return {"version":"futures-adaptive-1","mode":"synthetic","currency":"USDT","initial_capital":str(START),
            "shadow":summary(shadow),"double_cost_shadow":summary(stress),
            "decisions":decisions,"selection_counts":{n:counts[n] for n in (*CANDIDATES,"cash")},
            "evidence_blocks":blocks,"replay_quarantine":states,"next_regime":next_regime,"next_research_candidate":choice,
            "real_orders":False,"paper_orders":False,"promotion_enabled":False,
            "limitations":["Yalnız sentetik geçmiş replay; canlı ileri test veya ana sanal kasa değildir.",
                           "20 gözlemli blok, önceki bloklardan aday seçimi; en az 40 rejim gözlemi, 20 geçmiş işlem ve pozitif çift maliyet ortalaması.",
                           "Tek bir baz veya maliyet stres likidasyonu, iki aktif kayıp bloğu veya %10 üzeri düşüş karantina nedenidir.",
                           "Üç yeni olumlu aktif blok ve sıfır likidasyon yeniden izleme sağlar.",
                           "Her blok ayrı 1000 USDT ile boyutlanır; bileşik gölge sonuçları gerçek kasa veya global risk freni değildir.",
                           "Turnuva ve adaptif replay aynı sentetik veriyi kullanır; bağımsız doğrulama olarak birleştirilmez."]}
