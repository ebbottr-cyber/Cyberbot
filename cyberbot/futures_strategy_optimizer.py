"""Causal Futures strategy selection over local observations; not a paper ledger.

Fixed-size notional return proxies use next-minute entry, sampled exit, spread,
fees and slippage. No intraperiod fills, stop or liquidation simulation.
"""
import argparse,json,os
from . import futures_lightgbm as batch,futures_river as online
from . import futures_ai_memory as memory
from .futures import FEE,SLIP
from .observed_pilot import utc

VERSION="futures-strategy-optimizer-1"
NAMES=("lightgbm","river","agreement","momentum")
BLOCK=10
MIN_BLOCKS=3
MIN_TRADES=10
STEP=batch.HORIZON+1
REQUIRES={"lightgbm":("lightgbm",),"river":("river",),"agreement":("lightgbm","river"),"momentum":()}

def signal(x):
    return 1 if x>batch.COST_THRESHOLD else -1 if x<-batch.COST_THRESHOLD else 0

def forecasts(rows,train,test,*,batch_factory,online_factory):
    fixed=batch_factory();adaptive=online_factory()
    fixed.fit([x for _,x,_ in train],[y for _,_,y in train])
    a=list(fixed.predict([x for _,x,_ in test]))
    if len(a)!=len(test):raise batch.ResearchError("Tahmin sayısı uyuşmuyor.")
    # River learns only targets strictly before the current feature timestamp.
    examples=batch.build(rows);cursor=0;out=[]
    for k,(i,x,_) in enumerate(test):
        while cursor<len(examples) and examples[cursor][0]+batch.HORIZON<i:
            _,old_x,y=examples[cursor];adaptive.learn_one(dict(zip(batch.FEATURES,old_x)),y);cursor+=1
        guess=adaptive.predict_one(dict(zip(batch.FEATURES,x)))
        l=signal(batch.numeric(a[k],-1,1));r=signal(batch.numeric(0 if guess is None else guess,-1,1))
        out.append((i,{"lightgbm":l,"river":r,"agreement":l if l==r else 0,"momentum":signal(x[1])}))
    return out

def proxy(rows,i,side,multiplier):
    # A decision at i cannot fill at i. Exit at the model's original target time.
    if side not in (-1,0,1) or multiplier not in (1,2):raise batch.ResearchError("Senaryo geçersiz.")
    if not side:return None
    a,z=rows[i+1],rows[i+batch.HORIZON]
    # Funding amount is not observed settlement: exclude crossing intervals.
    if int(rows[i]["at"].timestamp())//28800!=int(z["at"].timestamp())//28800:return None
    if a["spread_bps"]>20:return None
    slip=float(SLIP)*multiplier;fee=float(FEE)*multiplier
    entry=a["mid"]*(1+side*(a["spread_bps"]/20000*multiplier+slip))
    exit=z["mid"]*(1-side*(z["spread_bps"]/20000*multiplier+slip))
    if entry<=0 or exit<=0:raise batch.ResearchError("Geçersiz modellenmiş fiyat.")
    return side*(exit-entry)/entry-fee*(1+exit/entry)

def initial():return {"blocks":0,"trades":0,"base_sum":0.0,"stress_sum":0.0,"weak":0,"recovery":0,"quarantined":False}
def update(s,base,stress):
    out=dict(s)
    if len(base)!=len(stress):raise batch.ResearchError("Maliyet senaryoları uyuşmuyor.")
    out["blocks"]+=1;out["trades"]+=len(base)
    out["base_sum"]+=sum(base);out["stress_sum"]+=sum(stress)
    if not base:return out
    good=sum(base)>0 and sum(stress)>0
    if out["quarantined"]:
        out["recovery"]=out["recovery"]+1 if good else 0
        if out["recovery"]>=3:out.update(quarantined=False,weak=0,recovery=0)
    else:
        out["weak"]=0 if good else out["weak"]+1
        if out["weak"]>=2:out.update(quarantined=True,recovery=0)
    return out

def choose(states,excluded=()):
    candidates=[k for k,s in states.items() if k not in excluded and not s["quarantined"]
                and s["blocks"]>=MIN_BLOCKS and s["trades"]>=MIN_TRADES
                and min(s["base_sum"],s["stress_sum"])>0]
    if not candidates:return "cash"
    # Compare per-trade stress returns; tie goes to cash, not arbitrary candidate.
    ranked=sorted(candidates,key=lambda k:states[k]["stress_sum"]/states[k]["trades"],reverse=True)
    if len(ranked)>1 and abs(states[ranked[0]]["stress_sum"]/states[ranked[0]]["trades"]-
                             states[ranked[1]]["stress_sum"]/states[ranked[1]]["trades"])<1e-9:return "cash"
    return ranked[0]

def memory_exclusions(snapshot,symbol,as_of):
    if (snapshot.get("symbol")!=symbol or snapshot.get("version")!=memory.VERSION
        or snapshot.get("data_mode")!="local_observations_unverified"):
        raise batch.ResearchError("AI hafıza kapsamı geçersiz.")
    states=snapshot["states"]
    excluded=[]
    for k,deps in REQUIRES.items():
        for model in deps:
            s=states[model];end=s.get("last_end")
            if end is not None and batch.timestamp(end)>as_of:
                raise batch.ResearchError("Gelecek AI hafıza kaydı.")
            if s.get("status")!="observing" or s.get("runs",0)<1 or s.get("weak_streak")!=0:
                excluded.append(k);break
    return excluded

def evaluate(raw,*,symbol,as_of,prior_memory=None,batch_factory=None,online_factory=None):
    rows=batch.validate(raw,symbol,as_of)
    examples=batch.build(rows);train,test,purged=batch.split(examples)
    injected=batch_factory is not None or online_factory is not None
    if injected and (batch_factory is None or online_factory is None):raise batch.ResearchError("İki deneme modeli gerekli.")
    if not injected:batch_factory=batch.estimator;online_factory,_=online.factories()
    observations=forecasts(rows,train,test,batch_factory=batch_factory,online_factory=online_factory)[::STEP]
    states={k:initial() for k in NAMES};blocks=[];selected_base=[];selected_stress=[]
    for start in range(0,len(observations)-BLOCK+1,BLOCK):
        block=observations[start:start+BLOCK]
        candidate=choose(states)
        outcomes={}
        for name in NAMES:
            base=[];stress=[]
            for i,votes in block:
                a=proxy(rows,i,votes[name],1);z=proxy(rows,i,votes[name],2)
                if a is not None:base.append(a);stress.append(z)
            outcomes[name]=(base,stress)
        if candidate!="cash":
            a,z=outcomes[candidate];selected_base.extend(a);selected_stress.extend(z)
        blocks.append({"first_feature_at":rows[block[0][0]]["at"].isoformat(),
                       "last_target_at":rows[block[-1][0]+batch.HORIZON]["at"].isoformat(),
                       "selected_before_block":candidate,
                       "prior_blocks":start//BLOCK,
                       "candidate_trades":len(outcomes[candidate][0]) if candidate!="cash" else 0,
                       "candidate_proxy_pct":sum(outcomes[candidate][0])*100 if candidate!="cash" else 0,
                       "candidate_double_cost_proxy_pct":sum(outcomes[candidate][1])*100 if candidate!="cash" else 0})
        # Selection never sees these results until the entire block has resolved.
        states={name:update(states[name],*outcomes[name]) for name in NAMES}
    excluded=list(NAMES) if prior_memory is None else memory_exclusions(prior_memory,symbol,as_of)
    next_candidate=choose(states,excluded)
    metrics={k:{**s,"base_sum_pct":s["base_sum"]*100,"stress_sum_pct":s["stress_sum"]*100}
             for k,s in states.items()}
    return {"version":VERSION,"status":"offline_strategy_research","symbol":symbol,
            "data_mode":"local_observations_unverified","observations":len(rows),
            "horizon_minutes":batch.HORIZON,"entry_delay_minutes":1,"sampling_stride_minutes":STEP,
            "training_examples":len(train),"purged_examples":purged,"completed_blocks":len(blocks),
            "unused_tail_slots":len(observations)%BLOCK,"blocks":blocks,"strategies":metrics,
            "selected_trade_count":len(selected_base),"selected_proxy_sum_pct":sum(selected_base)*100,
            "selected_double_cost_proxy_sum_pct":sum(selected_stress)*100,
            "next_research_candidate":next_candidate,"memory_excluded":excluded,
            "memory_used_for_replay":False,"memory_independent_evidence":False,
            "estimator_injected":injected,"runtime_verified":not injected,
            "position_sizing_verified":False,"stop_or_liquidation_simulated":False,
            "funding_crossings_excluded":True,"profitability_verified":False,
            "promotion_enabled":False,"actual_action":"HOLD","paper_orders":False,"real_orders":False}

def run(raw,*,symbol,as_of):
    flags=("CYBERBOT_FUTURES_STRATEGY_OPTIMIZER_ENABLED","CYBERBOT_FUTURES_LIGHTGBM_ENABLED",
           "CYBERBOT_FUTURES_RIVER_ENABLED","CYBERBOT_FUTURES_AI_MEMORY_ENABLED")
    if any(os.getenv(k)!="1" for k in flags):raise batch.ResearchError("Strateji araştırma izinleri kapalı.")
    return evaluate(raw,symbol=symbol,as_of=as_of,prior_memory=memory.snapshot(symbol))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True);p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"))
    a=p.parse_args()
    try:
        print(json.dumps(run(batch.read_local(a.input),symbol=a.symbol,as_of=utc()),ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
