"""Causal shadow-only regime allocation; no paper ledger or order calls."""
from datetime import date
from decimal import Decimal as D
from collections import Counter
from .capital import CAPITAL
from .engine import FEE,SLIP
from .learning import TRAIN,TEST,WINDOWS
from .strategy_lab import simulate,STRATEGIES
from .regimes import classify,REGIMES
from .robustness import metrics,returns_from
from .strategy_memory import initial,update,filter_choice

CANDIDATES=("trend","momentum","reversion")
MIN_REGIME_OBSERVATIONS=40
MIN_TRADES=20
MIN_MEAN_EDGE=.0002
MAX_DD=.10
RECENT_FOLDS=6

def decide(regime,evidence):
    ranking=[]
    for name in CANDIDATES:
        records=evidence[name]
        conditional=[(r,c) for fold in records for label,r,c in fold["observations"] if label==regime]
        recent=records[-RECENT_FOLDS:]
        recent_returns=[r for fold in recent for _,r,_ in fold["observations"]]
        net,dd=metrics(recent_returns)
        n=len(conditional);trades=sum(f["closed"] for f in records)
        avg=sum(r for r,_ in conditional)/n if n else 0.
        costly=sum(c for _,c in conditional)/n if n else 0.
        checks={"sample":n>=MIN_REGIME_OBSERVATIONS and trades>=MIN_TRADES,
                "net_edge":avg>=MIN_MEAN_EDGE,"double_cost_edge":costly>0,
                "recent_net":net>0,"recent_drawdown":dd<=MAX_DD}
        ranking.append({"strategy":name,"name":STRATEGIES[name],"observations":n,"prior_closed_trades":trades,
                       "mean_net_pct":round(avg*100,5) if n else None,"mean_double_cost_pct":round(costly*100,5) if n else None,
                       "recent_net_pct":round(net*100,5),"recent_drawdown_pct":round(dd*100,5),
                       "eligible":all(checks.values()),"checks":checks})
    ranking.sort(key=lambda x:(not x["eligible"],-(x["mean_double_cost_pct"] if x["mean_double_cost_pct"] is not None else -1e9),x["strategy"]))
    eligible=[x for x in ranking if x["eligible"]]
    return {"strategy":eligible[0]["strategy"] if eligible else "cash","ranking":ranking,
            "reason":"shadow_candidate" if eligible else "insufficient_or_weak_evidence"}

def evaluate(raw,*,mode,market,symbol):
    if mode not in ("synthetic","historical_unverified") or market not in CAPITAL:
        raise ValueError("Geçersiz piyasa veya veri modu.")
    if not 240<=len(raw)<=1000:raise ValueError("240–1000 gözlem gerekli.")
    bars=[];previous=None
    for row in raw:
        o,c=(D(str(row[k])) for k in ("open","close"))
        if any(not v.is_finite() or not D("1e-12")<=v<=D("1e9") for v in (o,c)):raise ValueError("Geçersiz fiyat.")
        if mode=="historical_unverified":
            session=date.fromisoformat(row["session"])
            if previous is not None and session<=previous:raise ValueError("Tarih sırası geçersiz.")
            previous=session
        bars.append((o,c))
    closes=[x[1] for x in bars]
    evidence={name:[] for name in CANDIDATES}
    quarantine={name:initial() for name in CANDIDATES};evidence_blocks=[]
    decisions=[];shadow=[];stress=[];benchmark=[];fixed={name:[] for name in CANDIDATES}
    for start in range(TRAIN,len(bars)-TEST+1,TEST):
        end=start+TEST
        # Select only from completed folds. Freeze the regime and policy for the next block.
        regime=classify(closes[:start])["id"]
        choice=filter_choice(decide(regime,evidence),quarantine)
        selected=choice["strategy"]
        windows={name:max(WINDOWS,key=lambda w:simulate(bars,name,w,start-TRAIN+20,start)["return"]) for name in CANDIDATES}
        results={}
        for name in CANDIDATES:
            base=simulate(bars,name,windows[name],start,end)
            costly=simulate(bars,name,windows[name],start,end,fee=FEE*2,slip=SLIP*2)
            results[name]=(base,costly)
            fixed[name].extend(returns_from(base))
        if selected=="cash":
            base=costly=simulate(bars,"cash",3,start,end)
        else:
            base,costly=results[selected]
        shadow.extend(returns_from(base));stress.extend(returns_from(costly))
        benchmark.extend(returns_from(simulate(bars,"buy_hold",3,start,end)))
        decisions.append({"start":start,"end_exclusive":end,"regime":regime,"selected":selected,
                          "reason":choice["reason"],"window":windows.get(selected),
                          "evidence_folds":len(evidence[CANDIDATES[0]]),"ranking":choice["ranking"],
                          "shadow_return_pct":round(float(base["return"])*100,5),"closed_trades":base["closed"]})
        # Reveal outcomes only after this block has finished. Attribute returns to the block-start
        # regime, matching the regime used when selecting policy for a whole block.
        for name,(b,c) in results.items():
            evidence[name].append({"closed":b["closed"],"observations":[(regime,r,s) for r,s in zip(returns_from(b),returns_from(c))]})
            block={"strategy":name,"regime":regime,
                   "start_key":raw[start]["session"] if mode=="historical_unverified" else f"{start:06d}",
                   "end_key":raw[end-1]["session"] if mode=="historical_unverified" else f"{end-1:06d}",
                   "return_pct":float(b["return"]*100),"double_cost_return_pct":float(c["return"]*100),
                   "drawdown_pct":float(b["drawdown"]*100),"double_cost_drawdown_pct":float(c["drawdown"]*100),"closed_trades":b["closed"]}
            evidence_blocks.append(block)
            quarantine[name]=update(quarantine[name],block)
    currency,capital=CAPITAL[market]
    def summary(rets):
        net,dd=metrics(rets)
        return {"return_pct":round(net*100,5),"drawdown_pct":round(dd*100,5),
                "ending_capital":str((capital*(1+D(str(net)))).quantize(D(".01")))}
    next_regime=classify(closes)
    next_choice=filter_choice(decide(next_regime["id"],evidence),quarantine)
    curve=[];wealth=1.
    for i,ret in enumerate(shadow,TRAIN):
        wealth*=1+ret
        curve.append({"observation":i,"equity":str((capital*D(str(wealth))).quantize(D(".01")))})
    counts=Counter(x["selected"] for x in decisions)
    return {"version":"adaptive-shadow-2","mode":mode,"market":market,"symbol":symbol,"currency":currency,"initial_capital":str(capital),
            "observations":len(bars),"completed_blocks":len(decisions),"shadow":summary(shadow),"double_cost_shadow":summary(stress),
            "buy_hold_reference":summary(benchmark),"cash_reference":summary([0.]*len(shadow)),
            "fixed_strategy_references":{k:summary(v) for k,v in fixed.items()},
            "evidence_blocks":evidence_blocks,"replay_quarantine":quarantine,"decisions":decisions,"selection_counts":{k:counts[k] for k in (*CANDIDATES,"cash")},"curve":curve,
            "next_regime":next_regime,"next_research_candidate":next_choice,
            "real_orders":False,"paper_orders":False,"promotion_enabled":False,"profitability_verified":False,
            "limits":["Gölge geçmiş testi, canlı ileri test değildir. Ana portföye emir göndermez.",
                      "20 gözlem başında önceki kapanışlarla rejim belirlenir; seçim blok boyunca sabittir.",
                      "Aday seçimi yalnız tamamlanmış bloklardan; pencere yalnız geçmiş eğitimden seçilir.",
                      "En az 40 aynı rejim gözlemi ve 20 geçmiş toplam kapanış; ortalama net getiri en az %0,02, iki kat maliyette pozitif; son 6 blok net pozitif, düşüş en fazla %10.",
                      "Bu eşikler deneysel ve kalibre edilmemiştir. Rejim gözlemleri bağımsız değildir; tam sermaye tahsisi, blok sonunda kapama, gerçek likidite veya kur modeli yoktur."]}
