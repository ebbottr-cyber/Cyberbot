"""Same-currency price-only portfolio research; no orders or automatic rebalance."""
import sqlite3
from contextlib import closing
import math

def optimize(database, market, symbols, currency, source, *, max_weight=0.25, min_observations=60):
    import numpy as np
    from scipy.optimize import minimize
    symbols=list(symbols)
    n=len(symbols)
    if market not in ("TEFAS","ETF") or n<2 or len(set(symbols))!=n or not 0<max_weight<=1 or n*max_weight<1-1e-10 or min_observations<60:
        raise ValueError("Invalid portfolio constraints")
    with closing(sqlite3.connect(database)) as db, db:
        histories={s:dict(db.execute("SELECT session,close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=?",(market,s,currency,source))) for s in symbols}
    dates=sorted(set.intersection(*(set(h) for h in histories.values())))
    if len(dates)<min_observations+1:
        return {"status":"insufficient_common_history","real_orders":False}
    prices=np.array([[float(histories[s][d]) for s in symbols] for d in dates])
    if not np.isfinite(prices).all() or (prices<=0).any():
        raise ValueError("Invalid prices")
    returns=prices[1:]/prices[:-1]-1
    cov=np.cov(returns,rowvar=False)
    if not np.isfinite(cov).all() or (np.diag(cov)<=0).any():
        return {"status":"invalid_covariance","real_orders":False}
    # Shrink off-diagonal estimates to reduce sensitivity to historical noise.
    cov=.8*cov+.2*np.diag(np.diag(cov))
    scale=max(float(np.max(np.diag(cov))),1e-12)
    result=minimize(lambda w:float(w@cov@w)/scale,np.full(n,1/n),method="SLSQP",bounds=[(0,max_weight)]*n,constraints=[{"type":"eq","fun":lambda w:float(w.sum()-1)}],options={"ftol":1e-10,"maxiter":500})
    w=result.x
    if not result.success or not np.isfinite(w).all() or abs(w.sum()-1)>1e-7 or (w< -1e-8).any() or (w>max_weight+1e-8).any():
        return {"status":"optimization_failed","real_orders":False}
    return {"status":"research_only","market":market,"currency":currency,"source":source,"symbols":symbols,"weights":dict(zip(symbols,map(float,w))),"correlation":np.corrcoef(returns,rowvar=False).tolist(),"historical_observation_volatility":math.sqrt(max(0,float(w@cov@w))),"observations":len(returns),"last_session":dates[-1],"max_weight":max_weight,"real_orders":False,"total_return_verified":False}

def rebalance_preview(target_weights,current_weights,*,threshold=0.05):
    if not 0<=threshold<=1:
        raise ValueError("Invalid threshold")
    for weights in (target_weights,current_weights):
        if not weights or any(not math.isfinite(v) or not 0<=v<=1 for v in weights.values()) or abs(sum(weights.values())-1)>1e-6:
            raise ValueError("Weights must sum to one")
    changes={s:target_weights.get(s,0)-current_weights.get(s,0) for s in sorted(set(target_weights)|set(current_weights))}
    return {"status":"review_only","weight_changes":changes,"turnover":sum(abs(v) for v in changes.values())/2,"review_required":any(abs(v)>threshold for v in changes.values()),"real_orders":False}
