"""Independent synthetic futures research; one-observation positions, no execution."""
import hashlib,json
from decimal import Decimal as D
from .futures import START,FEE,SLIP,LEVERAGE,MMR,FUNDING,SERIES
from .regimes import demo_rows,classify
from .robustness import bootstrap,metrics,score
from .analysis import review
from .models import evaluate as forecasts

VERSION="futures-research-2"
NAMES={"trend":"Çift yönlü trend","momentum":"Çift yönlü momentum","reversion":"Ortalamaya dönüş","long":"LONG referansı","short":"SHORT referansı","cash":"Nakit referansı"}
WINDOWS=(5,10,20)
HOLDOUT=60
BLOCK=20

def rows_for(symbol):
    if symbol not in SERIES:raise ValueError("Bilinmeyen sentetik sözleşme.")
    raw=demo_rows("NASDAQ" if symbol=="BTCUSDT" else "SOLANA")
    scale=SERIES[symbol][0]/100
    return [{"open":str(D(x["open"])*scale),"close":str(D(x["close"])*scale)} for x in raw]

def direction(name,past,w):
    if name=="cash":return 0
    if name=="long":return 1
    if name=="short":return -1
    p=past[-1]
    reference=past[-w] if name=="momentum" else sum(past[-w:])/w
    delta=p/reference-1
    if name=="reversion":return -1 if delta>D(".02") else 1 if delta<D("-.02") else 0
    return (delta>0)-(delta<0)

def simulate(bars,name,w,start,end,multiplier=1):
    """Flat at each observation boundary; previous close signal, next open to close."""
    cash=peak=START;dd=D(0);rets=[];closed=0;liquidations=0;longs=shorts=0
    funding_total=D(0);fees_total=D(0)
    fee=FEE*multiplier;slip=SLIP*multiplier
    for i in range(start,end):
        before=cash
        side=direction(name,[x[1] for x in bars[i-w:i]],w)
        if cash<=peak*D(".90") or cash<=START*D(".97"):side=0
        if side:
            o,c=bars[i];sign=D(side)
            entry=o*(1+sign*slip);exit_price=c*(1-sign*slip)
            stop=entry*(1-sign*D(".05"));exit_stop=stop*(1-sign*slip)
            unit=abs(entry-exit_stop)+entry*fee+exit_stop*fee
            qty=min(cash*D(".005")/unit,cash*D(".10")*LEVERAGE/entry,cash/(entry*(1/LEVERAGE+fee)))
            margin=qty*entry/LEVERAGE
            entry_fee=qty*entry*fee;exit_fee=qty*exit_price*fee
            funding=-sign*qty*c*FUNDING if i%3==0 else D(0)
            residual=margin+qty*sign*(exit_price-entry)-exit_fee+funding
            if residual<=qty*c*MMR:
                recovered=D(0);liquidations+=1
            else:recovered=max(D(0),residual)
            cash+=recovered-margin-entry_fee
            funding_total+=funding;fees_total+=entry_fee+exit_fee
            closed+=1;longs+=side==1;shorts+=side==-1
        peak=max(peak,cash);dd=max(dd,1-cash/peak)
        rets.append(float(cash/before-1))
    return {"returns":rets,"net":float(cash/START-1),"dd":float(dd),"closed":closed,"liquidations":liquidations,"longs":longs,"shorts":shorts,
            "funding_usdt":str(funding_total.quantize(D(".0001"))),"modeled_fees_usdt":str(fees_total.quantize(D(".0001")))}

def evaluate(raw,symbol):
    if symbol not in SERIES or not 240<=len(raw)<=1000:raise ValueError("240–1000 sentetik gözlem gerekli.")
    bars=[tuple(D(str(x[k])) for k in ("open","close")) for x in raw]
    if any(not v.is_finite() or not D("1e-12")<=v<=D("1e9") for pair in bars for v in pair):raise ValueError("Geçersiz fiyat.")
    split=len(bars)-HOLDOUT;ranking=[]
    for name,label in NAMES.items():
        returns=[];stress=[];positive=closed=folds=0;liqs=0;longs=shorts=0
        for i in range(60,split-BLOCK+1,BLOCK):
            w=max(WINDOWS,key=lambda w:simulate(bars,name,w,i-40,i)["net"])
            a=simulate(bars,name,w,i,i+BLOCK);b=simulate(bars,name,w,i,i+BLOCK,2)
            returns+=a["returns"];stress+=b["returns"];folds+=1;positive+=a["net"]>0
            closed+=a["closed"];liqs+=a["liquidations"];longs+=a["longs"];shorts+=a["shorts"]
        net,dd=metrics(returns);cost_net,_=metrics(stress);mc=bootstrap(returns)
        rating=score(folds=folds,trades=closed,positive=positive,net=net,dd=dd,cost_net=cost_net,mc=mc,reference=name in ("long","short","cash"))
        ranking.append({"id":name,"name":label,"return_pct":round(net*100,5),"drawdown_pct":round(dd*100,5),"double_cost_return_pct":round(cost_net*100,5),
                        "closed_trades":closed,"long_trades":longs,"short_trades":shorts,"liquidations":liqs,"monte_carlo":mc,**rating})
    ranking.sort(key=lambda x:(x["status"]!="research_candidate",-(x["score"] if x["score"] is not None else -1),x["id"]))
    eligible=[x for x in ranking if x["status"]=="research_candidate" and x["score"]>=65 and x["liquidations"]==0]
    candidate=eligible[0]["id"] if eligible and (len(eligible)==1 or eligible[0]["score"]-eligible[1]["score"]>=5) else None
    validation=None;champion=None
    if candidate:
        w=max(WINDOWS,key=lambda w:simulate(bars,candidate,w,20,split)["net"])
        a=simulate(bars,candidate,w,split,len(bars));b=simulate(bars,candidate,w,split,len(bars),2)
        validation={"window":w,"return_pct":round(a["net"]*100,5),"double_cost_return_pct":round(b["net"]*100,5),"drawdown_pct":round(a["dd"]*100,5),"closed_trades":a["closed"],"liquidations":a["liquidations"]}
        if a["net"]>0 and b["net"]>0 and max(a["dd"],b["dd"])<=.10 and a["closed"]>=5 and not (a["liquidations"] or b["liquidations"]):champion=candidate
    prices=[x["close"] for x in raw]
    regime=classify(prices)
    return {"version":VERSION,"mode":"synthetic","market":"FUTURES","symbol":symbol,"currency":"USDT","initial_capital":"1000","observations":len(raw),
            "ranking":ranking,"candidate":candidate,"research_champion":champion,"validation":validation,"regime":regime,
            "analysis":review(symbol,raw,mode="synthetic",source="sentetik futures araştırması"),
            "models":forecasts(prices,mode="synthetic"),"chronos_runtime_verified":False,
            "real_orders":False,"paper_orders":False,"promotion_enabled":False,"profitability_verified":False,
            "limitations":["Tek gözlem açık-kapanış pozisyonları, ayrı araştırma simülatörü; ana Futures defteri değildir.",
                           "2x izole teminat, varsayımsal ücret/kayma/fonlama, kapanışta basitleştirilmiş likidasyon; gün içi hareketler ve gerçek borsa kuralları yok.",
                           "Her blok 1000 USDT ile başlar; %3 kayıp ve %10 zirve düşüşü giriş freni blok bazındadır.",
                           "Aday seçimi son 60 gözlemi kullanmaz. Monte Carlo yalnız keşif ileri test getirileri; gerçek kârlılık kanıtı değil.",
                           "Sentetik BTC/ETH serisi; canlı bağlantı ve gerçek model çalışması yok."]}

def run_job(symbol):
    from .research_pipeline import PipelineJournal,research_path
    rows=rows_for(symbol)
    key=hashlib.sha256(json.dumps([VERSION,symbol,rows],sort_keys=True,separators=(",",":")).encode()).hexdigest()
    journal=PipelineJournal(research_path())
    previous=journal.get(key)
    if previous:
        return {"status":"duplicate","id":key,"market":"FUTURES","symbol":symbol,"summary":previous["summary"]}
    result=evaluate(rows,symbol)
    from .futures_adaptive import evaluate as adaptive_evaluate
    from .strategy_memory import StrategyMemory,filter_choice
    adapt=adaptive_evaluate([tuple(D(str(x[k])) for k in ("open","close")) for x in rows])
    mem=StrategyMemory(research_path()).record({**adapt,"market":"FUTURES","symbol":symbol})
    adapt["memory"]=mem
    adapt["next_research_candidate"]=filter_choice(adapt["next_research_candidate"],mem["states"])
    result["adaptive"]=adapt
    result["id"]=key
    result["summary"]={"regime":result["regime"]["id"],"tournament_status":"validated_research_candidate" if result["research_champion"] else "no_validated_candidate",
                       "research_champion":result["research_champion"],"next_candidate":adapt["next_research_candidate"]["strategy"],
                       "quarantined":[n for n,s in mem["states"].items() if s["status"]=="quarantined"],"new_evidence":mem["accepted"],"shadow_return_pct":adapt["shadow"]["return_pct"],"shadow_drawdown_pct":adapt["shadow"]["drawdown_pct"],"stages":6}
    return {"status":"new" if journal.save(result) else "duplicate","id":key,"market":"FUTURES","symbol":symbol,"summary":result["summary"]}
