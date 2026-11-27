"""Price-only hypothetical backtest; no settlement or executable fills."""
import math
import sqlite3
from datetime import date

def backtest(database, market, symbol, currency, source, *, initial_cash, cost_bps, lookback=20, execution_lag=1):
    if market not in ("TEFAS","ETF") or not math.isfinite(initial_cash) or initial_cash<=0 or not math.isfinite(cost_bps) or not 0<=cost_bps<10000 or not isinstance(lookback,int) or lookback<2 or not isinstance(execution_lag,int) or execution_lag<1:
        raise ValueError("Invalid simulation parameters")
    with sqlite3.connect(database) as db:
        rows=db.execute("SELECT session,close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? ORDER BY session",(market,symbol,currency,source)).fetchall()
    if len(rows)<=lookback+execution_lag:
        return {"status":"insufficient_data","real_orders":False}
    prices=[float(r[1]) for r in rows]
    if any(not math.isfinite(p) or p<=0 for p in prices):
        raise ValueError("Invalid prices")
    if any(date.fromisoformat(r[0])>date.today() for r in rows):
        raise ValueError("Future observation")
    cash=float(initial_cash)
    units=0.0
    rate=cost_bps/10000
    peak=cash
    max_dd=0.0
    trades=[]
    equity=[]
    fees=0.0
    for i,p in enumerate(prices):
        j=i-execution_lag
        if j>=lookback:
            target=prices[j]>prices[j-lookback]
            if target and units==0:
                fee=cash*rate/(1+rate)
                units=(cash-fee)/p
                cash=0.0
                side="BUY"
            elif not target and units>0:
                gross=units*p
                fee=gross*rate
                cash=gross-fee
                units=0.0
                side="SELL"
            else:
                side=None
            if side:
                fees+=fee
                trades.append({"side":side,"signal_date":rows[j][0],"execution_date":rows[i][0],"price":p,"fee":fee})
        value=cash+units*p
        peak=max(peak,value)
        max_dd=max(max_dd,1-value/peak)
        equity.append({"date":rows[i][0],"value":value})
    benchmark=initial_cash/(1+rate)*prices[-1]/prices[lookback+execution_lag]
    return {"status":"research_only","market":market,"currency":currency,"source":source,"initial_cash":initial_cash,"final_marked_equity":equity[-1]["value"],"return_pct":100*(equity[-1]["value"]/initial_cash-1),"benchmark_price_return_pct":100*(benchmark/initial_cash-1),"max_drawdown_pct":100*max_dd,"fees":fees,"trades":trades,"equity":equity,"open_units":units,"cost_bps":cost_bps,"execution_lag_observations":execution_lag,"settlement_verified":False,"total_return_verified":False,"real_orders":False}
