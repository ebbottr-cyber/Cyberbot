"""Out-of-sample robustness research. Heuristic score, not calibrated probability."""
from datetime import date
from decimal import Decimal as D
from math import isfinite
from random import Random
from statistics import mean
from .strategy_lab import simulate, STRATEGIES
from .learning import WINDOWS, TRAIN, TEST
from .engine import FEE,SLIP
from .capital import CAPITAL

VERSION="robustness-1"
PATHS=1000
SEED=20261126
BLOCK=5
HORIZON=60
MIN_FOLDS=6
MIN_TRADES=20
DD_LIMIT=.10

def quantile(values,q):
    data=sorted(values)
    x=(len(data)-1)*q
    i=int(x)
    return data[i]+(data[min(i+1,len(data)-1)]-data[i])*(x-i)

def metrics(returns):
    wealth=peak=1.;dd=0.
    for v in returns:
        wealth*=1+v
        peak=max(peak,wealth)
        dd=max(dd,1-wealth/peak)
    return wealth-1,dd

def bootstrap(returns,*,block=BLOCK,paths=PATHS,horizon=HORIZON,seed=SEED):
    if not 1<=block<=len(returns) or not 1<=paths<=2000 or not 1<=horizon<=240:
        raise ValueError("Geçersiz simülasyon boyutu.")
    if any(not isfinite(x) or x<=-1 or x>100 for x in returns):
        raise ValueError("Geçersiz getiri.")
    rng=Random(seed)
    finals=[];drawdowns=[]
    for _ in range(paths):
        sample=[]
        while len(sample)<horizon:
            i=rng.randrange(len(returns)-block+1)
            sample.extend(returns[i:i+block])
        ret,dd=metrics(sample[:horizon])
        finals.append(ret);drawdowns.append(dd)
    return {"paths":paths,"block":block,"horizon":horizon,"seed":seed,
            "p05_return_pct":round(quantile(finals,.05)*100,4),
            "p50_return_pct":round(quantile(finals,.5)*100,4),
            "p95_return_pct":round(quantile(finals,.95)*100,4),
            "p95_drawdown_pct":round(quantile(drawdowns,.95)*100,4),
            "loss_path_pct":round(mean(x<0 for x in finals)*100,2),
            "drawdown_over_10_path_pct":round(mean(x>DD_LIMIT for x in drawdowns)*100,2)}

def score(*,folds,trades,positive,net,dd,cost_net,mc,reference=False):
    if reference:return {"score":None,"status":"reference","components":{}}
    clip=lambda x:max(0.,min(1.,x))
    parts={"consistency":25*positive/folds,
           "drawdown":25*clip(1-dd/DD_LIMIT),
           "cost_resilience":20*clip(cost_net/net) if net>0 and cost_net>0 else 0.,
           "bootstrap_downside":20*clip(1-mc["drawdown_over_10_path_pct"]/100)*clip(1-mc["loss_path_pct"]/100),
           "sample_size":10*min(1,folds/12)*min(1,trades/40)}
    enough=folds>=MIN_FOLDS and trades>=MIN_TRADES
    candidate=enough and net>0 and cost_net>0 and dd<=DD_LIMIT and positive*2>=folds and mc["p95_drawdown_pct"]<=10 and mc["loss_path_pct"]<=40
    return {"score":round(sum(parts.values()),1) if enough else None,
            "status":"research_candidate" if candidate else "weak" if enough else "insufficient_sample",
            "components":{k:round(v,2) for k,v in parts.items()}}

def returns_from(sim):
    # Each fold begins flat with the simulator's normalized research capital.
    prev=D("10000");result=[]
    for v in sim["equity"]:
        result.append(float(v/prev-1))
        prev=v
    return result

def evaluate(raw,*,mode,market,symbol):
    if mode not in ("synthetic","historical_unverified") or market not in CAPITAL:
        raise ValueError("Geçersiz piyasa veya veri modu.")
    if not 120<=len(raw)<=1000:raise ValueError("120–1000 gözlem gerekli.")
    bars=[];previous=None
    for row in raw:
        o,c=(D(str(row[k])) for k in ("open","close"))
        if any(not x.is_finite() or not D("1e-12")<=x<=D("1e9") for x in (o,c)):raise ValueError("Geçersiz fiyat.")
        if mode=="historical_unverified":
            session=date.fromisoformat(row["session"])
            if previous is not None and session<=previous:raise ValueError("Tarih sırası geçersiz.")
            previous=session
        bars.append((o,c))
    if any(max(bars[i])/min(bars[i-1])>D(101) for i in range(1,len(bars))):raise ValueError("Aşırı fiyat değişimi.")
    currency,capital=CAPITAL[market]
    rows=[]
    for name,label in STRATEGIES.items():
        returns=[];stress_returns=[];fold_results=[];trades=0;positive=0
        for start in range(TRAIN,len(bars)-TEST+1,TEST):
            window=max(WINDOWS,key=lambda w:simulate(bars,name,w,start-TRAIN+20,start)["return"]) if name not in ("cash","buy_hold") else 3
            base=simulate(bars,name,window,start,start+TEST)
            costly=simulate(bars,name,window,start,start+TEST,fee=FEE*2,slip=SLIP*2)
            returns.extend(returns_from(base));stress_returns.extend(returns_from(costly))
            trades+=base["closed"];positive+=base["return"]>0
            fold_results.append({"start":start,"end_exclusive":start+TEST,"window":window,"return_pct":round(float(base["return"])*100,4)})
        net,dd=metrics(returns);cost_net,cost_dd=metrics(stress_returns)
        mc=bootstrap(returns)
        mc["p05_ending_capital"]=str((capital*(1+D(str(mc["p05_return_pct"]))/100)).quantize(D(".01")))
        mc["p50_ending_capital"]=str((capital*(1+D(str(mc["p50_return_pct"]))/100)).quantize(D(".01")))
        mc["p95_ending_capital"]=str((capital*(1+D(str(mc["p95_return_pct"]))/100)).quantize(D(".01")))
        rating=score(folds=len(fold_results),trades=trades,positive=positive,net=net,dd=dd,cost_net=cost_net,mc=mc,reference=name in ("cash","buy_hold"))
        rows.append({"id":name,"name":label,"folds":fold_results,"fold_count":len(fold_results),"positive_folds":positive,"closed_trades":trades,
                     "oos_return_pct":round(net*100,4),"oos_drawdown_pct":round(dd*100,4),"double_cost_return_pct":round(cost_net*100,4),
                     "double_cost_drawdown_pct":round(cost_dd*100,4),"monte_carlo":mc,**rating})
    return {"version":VERSION,"mode":mode,"market":market,"symbol":symbol,"currency":currency,"initial_capital":str(capital),
            "observations":len(bars),"strategies":rows,"real_orders":False,"promotion_enabled":False,"profitability_verified":False,
            "score_calibrated":False,"score_weights":{"consistency":25,"drawdown":25,"cost_resilience":20,"bootstrap_downside":20,"sample_size":10},
            "limits":["Puan deneysel araştırma ölçütüdür; gerçek başarı olasılığı değildir.",
                      "Monte Carlo: yalnız ileri test getirilerinin 5 gözlemli blokları, 1000 yol ve 60 gözlem ufku; fiyat üretimi veya gerçek gün tahmini değildir.",
                      "İleri test bölümleri bağımsız kanıt değildir; tam sermaye tahsisi araştırma varsayımıdır, paper risk motoru değildir.",
                      "P05/P95 model içi yüzdeliklerdir, güven aralığı veya gelecek garantisi değildir.",
                      "Kurlar, likidite ve kurumsal işlemler modellenmez; otomatik strateji terfisi yok."]}
