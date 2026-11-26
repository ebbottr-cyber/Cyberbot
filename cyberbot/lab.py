"""Tiny example of causal historical research, using synthetic observations only."""
from decimal import Decimal as D
from .market import INDEX
from .engine import FEE, SLIP

def experiment(symbol):
    prices=INDEX[symbol].prices
    cash=D("10000")
    quantity=D(0)
    peak=cash
    max_dd=D(0)
    entries=0
    # Signal uses completed observations only; execution uses the next observation.
    for i in range(3,len(prices)):
        past=prices[:i]
        signal=past[-1]>sum(past[-3:])/3
        if signal and not quantity:
            quantity=cash/(prices[i]*(1+SLIP)*(1+FEE))
            cash=D(0)
            entries+=1
        elif not signal and quantity:
            cash=quantity*prices[i]*(1-SLIP)*(1-FEE)
            quantity=D(0)
        equity=cash+quantity*prices[i]*(1-SLIP)*(1-FEE)
        peak=max(peak,equity)
        max_dd=max(max_dd,1-equity/peak)
    final=cash+quantity*prices[-1]*(1-SLIP)*(1-FEE)
    return {"symbol":symbol,"mode":"synthetic","entries":entries,"return_pct":str(((final/D("10000")-1)*100).quantize(D("0.01"))),"max_drawdown_pct":str((max_dd*100).quantize(D("0.01")))}
