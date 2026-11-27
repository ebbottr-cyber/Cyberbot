"""Historical price-only research; no execution or predictive AI."""
import math
import sqlite3
from statistics import stdev
from datetime import date

def analyze(database, market, symbol, currency, source):
    with sqlite3.connect(database) as db:
        rows = db.execute("SELECT session, close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? ORDER BY session", (market,symbol,currency,source)).fetchall()
    if len(rows)<21:
        return {"status":"insufficient_data","observations":len(rows),"real_orders":False}
    prices=[float(r[1]) for r in rows]
    if any(not math.isfinite(p) or p<=0 for p in prices):
        raise ValueError("Invalid prices")
    returns=[b/a-1 for a,b in zip(prices,prices[1:])]
    peak=prices[0]
    drawdown=0
    for p in prices:
        peak=max(peak,p)
        drawdown=max(drawdown,1-p/peak)
    momentum=prices[-1]/prices[-21]-1
    return {"status":"research_only","market":market,"symbol":symbol,"currency":currency,
            "source":source,"observations":len(rows),"last_session":rows[-1][0],
            "age_days":(date.today()-date.fromisoformat(rows[-1][0])).days,
            "price_return_pct":100*(prices[-1]/prices[0]-1),
            "last_20_observation_return_pct":100*momentum,
            "observation_volatility_pct":100*stdev(returns),
            "max_drawdown_pct":100*drawdown,
            "explanation":"Historical price momentum positive" if momentum>0 else "Historical price momentum non-positive",
            "total_return_verified":False,"live_data_verified":False,"ai_prediction":False,"real_orders":False}
