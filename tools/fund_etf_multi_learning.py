"""Offline optional model challengers. No automatic promotion or orders."""
import math
import sqlite3

def evaluate(database, market, symbol, currency, source, *, min_train=100, horizon=5, step=20):
    if min_train<100 or horizon<1 or step<1:
        raise ValueError("Invalid evaluation parameters")
    from lightgbm import LGBMClassifier
    from xgboost import XGBClassifier
    from river import linear_model, preprocessing
    with sqlite3.connect(database) as db:
        rows=db.execute("SELECT session,close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? ORDER BY session",(market,symbol,currency,source)).fetchall()
    p=[float(r[1]) for r in rows]
    if any(not math.isfinite(v) or v<=0 for v in p):
        raise ValueError("Invalid prices")
    x=[]; y=[]; dates=[]
    for i in range(20,len(p)-horizon):
        x.append([p[i]/p[i-k]-1 for k in (1,5,20)])
        y.append(int(p[i+horizon]>p[i]))
        dates.append(rows[i][0])
    out={name:[] for name in ("LightGBM","XGBoost","River")}
    online=preprocessing.StandardScaler() | linear_model.LogisticRegression()
    learned=0
    for start in range(min_train+horizon,len(x),step):
        end=start-horizon
        if len(set(y[:end]))<2:
            continue
        models={"LightGBM":LGBMClassifier(n_estimators=50,max_depth=3,verbosity=-1,n_jobs=1,random_state=42),"XGBoost":XGBClassifier(n_estimators=50,max_depth=3,n_jobs=1,random_state=42)}
        for model in models.values():
            model.fit(x[:end],y[:end])
        while learned<end:
            online.learn_one(dict(enumerate(x[learned])),y[learned])
            learned+=1
        stop=min(start+step,len(x))
        baseline=int(sum(y[:end])*2>=end)
        for name,model in models.items():
            for j,prob in enumerate(model.predict_proba(x[start:stop])[:,1],start):
                out[name].append(dict(date=dates[j],probability=float(prob),actual=y[j],baseline=baseline))
        for j in range(start,stop):
            prob=online.predict_proba_one(dict(enumerate(x[j]))).get(True,0.5)
            out["River"].append(dict(date=dates[j],probability=float(prob),actual=y[j],baseline=baseline))
    return {name:{"status":"offline_research" if len(predictions)>=30 else "insufficient_evaluation","horizon_observations":horizon,"predictions":predictions,"model_promoted":False,"real_orders":False} for name,predictions in out.items()}
