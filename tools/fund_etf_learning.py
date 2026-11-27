"""Optional local ML research; no model promotion or execution."""
import math
import sqlite3

def evaluate(database, market, symbol, currency, source, *, min_train=100, horizon=5, step=20):
    if min_train<100 or horizon<1 or step<1:
        raise ValueError("Invalid evaluation parameters")
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    with sqlite3.connect(database) as db:
        rows=db.execute("SELECT session,close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? ORDER BY session",(market,symbol,currency,source)).fetchall()
    p=[float(r[1]) for r in rows]
    if any(not math.isfinite(x) or x<=0 for x in p):
        raise ValueError("Invalid prices")
    x=[]; y=[]; dates=[]
    for i in range(20,len(p)-horizon):
        x.append([p[i]/p[i-k]-1 for k in (1,5,20)])
        y.append(int(p[i+horizon]>p[i]))
        dates.append(rows[i][0])
    predictions=[]
    for start in range(min_train+horizon,len(x),step):
        end=start-horizon
        if len(set(y[:end]))<2:
            continue
        model=make_pipeline(StandardScaler(),LogisticRegression(max_iter=500,random_state=42))
        model.fit(x[:end],y[:end])
        stop=min(start+step,len(x))
        baseline=int(sum(y[:end])*2>=end)
        for j,prob in enumerate(model.predict_proba(x[start:stop])[:,1],start):
            predictions.append(dict(date=dates[j],probability=float(prob),actual=y[j],baseline=baseline))
    n=len(predictions)
    if n<30:
        return {"status":"insufficient_evaluation","observations":n,"real_orders":False}
    accuracy=sum(int((r["probability"]>=.5)==bool(r["actual"])) for r in predictions)/n
    baseline_accuracy=sum(r["baseline"]==r["actual"] for r in predictions)/n
    brier=sum((r["probability"]-r["actual"])**2 for r in predictions)/n
    return {"status":"offline_research","observations":n,"accuracy":accuracy,"baseline_accuracy":baseline_accuracy,"brier_score":brier,"beats_baseline":accuracy>baseline_accuracy,"horizon_observations":horizon,"predictions":predictions,"model_promoted":False,"real_orders":False}
