"""Optional CPU LightGBM Futures research. Local input only, no order or promotion path."""
import argparse,json,math,os
from datetime import datetime,timedelta,timezone
from pathlib import Path
from statistics import mean

VERSION="futures-lightgbm-1"
STEP=timedelta(minutes=1)
HORIZON=5
MAX_ROWS=6000
MIN_ROWS=240
MAX_BYTES=4*1024*1024
# Fixed research assumptions, not exchange fees or a profit guarantee.
COST_THRESHOLD=.004
FEATURES=("return_1m","return_5m","return_20m","spread_bps","funding_rate",
          "mark_index_basis_pct","open_interest_change_5m","book_imbalance",
          "taker_imbalance","atr_1m_pct","atr_5m_pct")
FIELDS={"at","symbol","source","mid","spread_bps","funding_rate","mark_index_basis_pct",
        "open_interest","book_imbalance","taker_imbalance","atr_1m_pct","atr_5m_pct"}

class ResearchError(ValueError):pass
def numeric(v,lo,hi):
    if isinstance(v,bool) or not isinstance(v,(str,int,float)):raise ResearchError("Sayısal alan geçersiz.")
    try:x=float(v)
    except (ValueError,OverflowError):raise ResearchError("Sayısal alan geçersiz.") from None
    if not math.isfinite(x) or not lo<=x<=hi:raise ResearchError("Sayısal alan sınırı.")
    return x

def timestamp(v):
    if not isinstance(v,str):raise ResearchError("UTC zaman damgası gerekli.")
    try:t=datetime.fromisoformat(v.replace("Z","+00:00"))
    except ValueError:raise ResearchError("UTC zaman damgası geçersiz.") from None
    if t.utcoffset()!=timedelta(0) or t.second or t.microsecond:
        raise ResearchError("Tam UTC dakika gerekli.")
    return t.astimezone(timezone.utc)

def validate(rows,symbol,as_of):
    if symbol not in ("BTCUSDT","ETHUSDT") or not isinstance(rows,list) or not MIN_ROWS<=len(rows)<=MAX_ROWS:
        raise ResearchError("240–6000 tek sembollü gözlem gerekli.")
    if not isinstance(as_of,datetime) or as_of.utcoffset() is None:raise ResearchError("Zaman dilimli kesim gerekli.")
    out=[]
    for row in rows:
        if (not isinstance(row,dict) or set(row)!=FIELDS or row["symbol"]!=symbol
            or row["source"]!="binance-usdm-public"):
            raise ResearchError("Gözlem şeması, sembolü veya kaynağı uyumsuz.")
        t=timestamp(row["at"])
        if t>as_of or (out and t-out[-1]["at"]!=STEP):
            raise ResearchError("Gelecek, eksik, tekrar veya sırasız dakika.")
        out.append({"at":t,"mid":numeric(row["mid"],1e-8,1e9),
                    "spread_bps":numeric(row["spread_bps"],0,20000),
                    "funding_rate":numeric(row["funding_rate"],-.1,.1),
                    "mark_index_basis_pct":numeric(row["mark_index_basis_pct"],-100,100),
                    "open_interest":numeric(row["open_interest"],1e-12,1e12),
                    "book_imbalance":numeric(row["book_imbalance"],-1,1),
                    "taker_imbalance":numeric(row["taker_imbalance"],-1,1),
                    "atr_1m_pct":numeric(row["atr_1m_pct"],0,100),
                    "atr_5m_pct":numeric(row["atr_5m_pct"],0,100)})
    return out

def features(rows,i):
    r=rows[i];p=r["mid"]
    values=[p/rows[i-k]["mid"]-1 for k in (1,5,20)]
    values.extend((r["spread_bps"],r["funding_rate"],r["mark_index_basis_pct"],
                   r["open_interest"]/rows[i-5]["open_interest"]-1,r["book_imbalance"],
                   r["taker_imbalance"],r["atr_1m_pct"],r["atr_5m_pct"]))
    if any(not math.isfinite(x) or abs(x)>1e9 for x in values):raise ResearchError("Özellik sınırı.")
    return values

def build(rows):
    examples=[]
    for i in range(20,len(rows)-HORIZON):
        target=rows[i+HORIZON]["mid"]/rows[i]["mid"]-1
        if abs(target)>1:raise ResearchError("Aşırı hedef fiyat değişimi.")
        examples.append((i,features(rows,i),target))
    return examples

def split(examples):
    # Chronological 70/30 split. Remove labels touching the first test feature time.
    cut=len(examples)*7//10
    test=examples[cut:]
    if not test:raise ResearchError("Test örneklemi eksik.")
    train=[row for row in examples[:cut] if row[0]+HORIZON<test[0][0]]
    if len(train)<100 or len(test)<50:raise ResearchError("Eğitim/test örneklemi eksik.")
    return train,test,cut-len(train)

def estimator():
    try:from lightgbm import LGBMRegressor
    except ImportError:raise ResearchError("İsteğe bağlı requirements-futures-ai.txt kurulmalı.") from None
    return LGBMRegressor(objective="regression_l1",n_estimators=64,max_depth=4,num_leaves=15,
                         min_child_samples=20,learning_rate=.05,n_jobs=1,random_state=42,
                         deterministic=True,force_col_wise=True,verbosity=-1)

def direction(value):
    return "UP" if value>COST_THRESHOLD else "DOWN" if value<-COST_THRESHOLD else "HOLD"

def metrics(pred,actual):
    if len(pred)!=len(actual) or not actual:raise ResearchError("Tahmin sayısı uyumsuz.")
    p=[numeric(x,-1,1) for x in pred]
    return {"mae_pct":mean(abs(a-b) for a,b in zip(p,actual))*100,
            "direction_accuracy_pct":mean(direction(a)==direction(b) for a,b in zip(p,actual))*100,
            "prediction_counts":{k:sum(direction(a)==k for a in p) for k in ("UP","DOWN","HOLD")}}

def evaluate(raw,*,symbol,as_of,model_factory=None):
    rows=validate(raw,symbol,as_of)
    examples=build(rows);train,test,purged=split(examples)
    x=[r[1] for r in train];y=[r[2] for r in train]
    model=(model_factory or estimator)()
    model.fit(x,y)
    predictions=list(model.predict([r[1] for r in test]))
    actual=[r[2] for r in test]
    # Fixed trailing momentum baseline uses only features at each prediction timestamp.
    baseline=[r[1][1] for r in test]
    model_metrics=metrics(predictions,actual)
    zero_metrics=metrics([0.0]*len(test),actual)
    momentum_metrics=metrics(baseline,actual)
    return {"version":VERSION,"status":"offline_research_only","symbol":symbol,
            "data_mode":"local_observations_unverified","observations":len(rows),
            "features":list(FEATURES),"target":"5_minute_midpoint_return","horizon_minutes":HORIZON,
            "cost_deadband_pct":COST_THRESHOLD*100,"training_examples":len(train),
            "test_examples":len(test),"purged_examples":purged,
            "training_last_target_at":rows[train[-1][0]+HORIZON]["at"].isoformat(),
            "test_first_feature_at":rows[test[0][0]]["at"].isoformat(),
            "test_last_target_at":rows[test[-1][0]+HORIZON]["at"].isoformat(),
            "metrics":{"lightgbm":model_metrics,"zero":zero_metrics,"trailing_momentum":momentum_metrics},
            "model_mae_below_both_baselines":model_metrics["mae_pct"]<min(zero_metrics["mae_pct"],momentum_metrics["mae_pct"]),
            "estimator_injected":model_factory is not None,"runtime_verified":model_factory is None,
            "feature_provenance_verified":False,"outcomes_overlap":True,
            "profitability_verified":False,"promotion_enabled":False,"model_saved":False,
            "actual_action":"HOLD","paper_orders":False,"real_orders":False}

def read_local(path):
    p=Path(path).expanduser()
    if not p.is_file():raise ResearchError("Yerel gözlem dosyası gerekli.")
    with p.open("rb") as file:data=file.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ResearchError("Gözlem dosyası boyut sınırı.")
    return json.loads(data)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True);p.add_argument("--symbol",choices=("BTCUSDT","ETHUSDT"),required=True)
    a=p.parse_args()
    try:
        if os.getenv("CYBERBOT_FUTURES_LIGHTGBM_ENABLED")!="1":raise ResearchError("LightGBM araştırma izni kapalı.")
        print(json.dumps(evaluate(read_local(a.input),symbol=a.symbol,as_of=datetime.now(timezone.utc)),
                         ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError) as exc:
        print(json.dumps({"status":"rejected","type":type(exc).__name__}));return 1

if __name__=="__main__":raise SystemExit(main())
