"""Rolling, causal strategy research gate from recorded forward predictions.

No promotion to real trading. Only agreement can qualify for the existing
paper entry path; other rules are comparison research, never order sources.
"""
import argparse,json,sqlite3
from contextlib import closing
from datetime import datetime,timezone,timedelta
from . import futures_lightgbm as batch,futures_forward_memory as forward
from . import futures_ai_bridge as bridge,futures_strategy_optimizer as opt
from . import observed_pilot as stocks

VERSION="futures-strategy-gate-1"
HOURS=6
BLOCKS=8
EXPECTED=HOURS*60//batch.HORIZON
MIN_SCORED=60
MIN_TRADES=10
GOOD_REQUIRED=3
WEAK_LIMIT=2

def initial():
    return {"state":"observing","good_streak":0,"weak_streak":0}
def advance(state,quality):
    s=dict(state)
    if quality=="insufficient":
        s.update(good_streak=0,weak_streak=0)
        if s["state"]!="quarantined":s["state"]="observing"
    elif quality=="good":
        s["good_streak"]+=1;s["weak_streak"]=0
        if s["good_streak"]>=GOOD_REQUIRED:s["state"]="paper_research_eligible"
    elif quality=="weak":
        s["good_streak"]=0;s["weak_streak"]+=1
        if s["weak_streak"]>=WEAK_LIMIT:s["state"]="quarantined"
        elif s["state"]!="quarantined":s["state"]="observing"
    else:raise ValueError("Bilinmeyen strateji sonucu.")
    return s

def evaluate_block(records,prices,start,end):
    # All scheduled five-minute targets count toward coverage, not just signals.
    # The five-minute issuance rhythm may have gaps; never invent them.
    scored=0;out={k:[] for k in opt.NAMES};stress={k:[] for k in opt.NAMES}
    previous=None
    for feature,target,issued,status,d in records:
        a=batch.timestamp(feature);z=batch.timestamp(target);t=stocks.ts(issued)
        if not start<=a<z<=end or z-a!=batch.HORIZON*batch.STEP or not a<=t<=a+timedelta(seconds=forward.MAX_ISSUE_AGE) or (previous and a<previous):
            raise ValueError("İleri tahmin zaman sırası.")
        previous=z
        if status in ("missing","pending"):continue
        if status!="scored" or not t<stocks.ts(d["target_received_at"])<z or not z<=stocks.ts(d["resolved_at"]):
            raise ValueError("İleri sonuç kimliği.")
        if stocks.ts(d["resolved_at"])>end:continue
        if d.get("model_versions")!={"lightgbm":batch.VERSION,"river":bridge.online.VERSION,"forecast":bridge.VERSION}:
            raise ValueError("Model sürümü uyuşmuyor.")
        window=[prices.get(a+i*batch.STEP) for i in range(batch.HORIZON+1)]
        if any(r is None for r in window):continue
        if window[0]["mid"]!=batch.numeric(d["feature_mid"],1e-8,1e9) or abs(window[-1]["mid"]/window[0]["mid"]-1-batch.numeric(d["actual_return"],-1,1))>1e-12:
            raise ValueError("Tahmin ve kaynak fiyat uyuşmuyor.")
        scored+=1
        l=opt.signal(batch.numeric(d["predictions"]["lightgbm"],-1,1))
        r=opt.signal(batch.numeric(d["predictions"]["river"],-1,1))
        votes={"lightgbm":l,"river":r,"agreement":l if l==r else 0,
               "momentum":opt.signal(batch.numeric(d["predictions"]["trailing_momentum"],-1,1))}
        for k,side in votes.items():
            x=opt.proxy(window,0,side,1);y=opt.proxy(window,0,side,2)
            if (x is None)!=(y is None):raise ValueError("Maliyet senaryosu uyuşmuyor.")
            if x is not None:out[k].append(x);stress[k].append(y)
    coverage=scored/EXPECTED
    strategies={}
    for k in opt.NAMES:
        n=len(out[k]);base=sum(out[k]);stressed=sum(stress[k])
        quality="insufficient" if scored<MIN_SCORED or coverage<.9 or n<MIN_TRADES else "good" if min(base,stressed)>0 else "weak"
        strategies[k]={"quality":quality,"trades":n,"base_proxy_sum_pct":base*100,"stress_proxy_sum_pct":stressed*100}
    return {"start":start.isoformat(),"end":end.isoformat(),"scored":scored,"expected_slots":EXPECTED,"coverage_pct":coverage*100,"strategies":strategies}

def report(symbol,*,clock=stocks.utc):
    if symbol not in ("BTCUSDT","ETHUSDT"):raise ValueError("Sembol geçersiz.")
    now=clock();end=datetime.fromtimestamp(int(now.timestamp())//(HOURS*3600)*(HOURS*3600),timezone.utc)
    start=end-timedelta(hours=HOURS*BLOCKS)
    states={k:initial() for k in opt.NAMES}
    out={"version":VERSION,"symbol":symbol,"as_of":now.isoformat(),"status":"waiting_for_evidence","states":states,"blocks":[],
         "agreement_gate":False,"actual_action":"HOLD","real_orders":False,"paper_orders":False,
         "promotion_to_real_enabled":False,"profitability_verified":False,"rolling_reconstruction":True}
    p=forward.path()
    if not p.is_file():return out
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
        if not forward.schema(db):return out
        records=db.execute("SELECT feature_at,target_at,issued_at,status,payload FROM "+forward.TABLE+
                          " WHERE symbol=? AND feature_at>=? AND target_at<=? ORDER BY feature_at",
                          (symbol,start.isoformat(),end.isoformat())).fetchall()
    if len(records)>BLOCKS*EXPECTED:raise ValueError("Tahmin yoğunluğu geçersiz.")
    if not records:return out
    rows=forward.exact_window(symbol,start,end,now)
    prices={}
    for rec in rows:
        row=rec["row"];at=batch.timestamp(row["at"])
        prices[at]={"at":at,"mid":batch.numeric(row["mid"],1e-8,1e9),"spread_bps":batch.numeric(row["spread_bps"],0,20000)}
    records=[(a,z,t,s,json.loads(d)) for a,z,t,s,d in records]
    previous=None
    for a,z,t,s,d in records:
        a=batch.timestamp(a);z=batch.timestamp(z)
        if previous and a<previous:raise ValueError("Örtüşen ileri tahmin.")
        previous=z
    for i in range(BLOCKS):
        a=start+timedelta(hours=i*HOURS);z=a+timedelta(hours=HOURS)
        block=evaluate_block([r for r in records if a<=batch.timestamp(r[0]) and batch.timestamp(r[1])<=z],prices,a,z)
        out["blocks"].append(block)
        for k in opt.NAMES:states[k]=advance(states[k],block["strategies"][k]["quality"])
    out["agreement_gate"]=states["agreement"]["state"]=="paper_research_eligible" and out["blocks"][-1]["strategies"]["agreement"]["quality"]=="good"
    out["status"]="evaluated";return out

def allowed(symbol,*,clock=stocks.utc):
    return report(symbol,clock=clock)["agreement_gate"] is True

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"));a=p.parse_args()
    try:print(json.dumps(report(a.symbol),ensure_ascii=True,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__,"agreement_gate":False,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
