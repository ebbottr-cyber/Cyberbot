"""Stress actual Futures ledger with isolated injected synthetic series."""
from collections import Counter
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from .futures import Futures,START
from .engine import PaperError

def run_futures(scenario,steps):
    from .stress import universe,LABELS
    base=list(universe(scenario,steps).values())[0].prices
    # Same deterministic scenario, independent synthetic contracts.
    series={"BTCUSDT":tuple(x*600 for x in base),"ETHUSDT":tuple(x*30 for x in base)}
    if scenario=="gap":
        # Force adverse discontinuities in both directions, not actual market prices.
        vals=list(series["BTCUSDT"]);vals[15]=vals[14]*D(".40");vals[steps//2]=vals[steps//2-1]*D("1.75")
        series["BTCUSDT"]=tuple(vals)
    with TemporaryDirectory(prefix="cyberbot-futures-stress-") as tmp:
        f=Futures(Path(tmp)/"f.sqlite3",series=series,day_clock=lambda:"2000-01-01")
        attempts=rejected=peak_open=0;violations=[];curve=[];side="LONG"
        for i in range(steps):
            s=f.snapshot()
            if s["tick"]!=i:violations.append("tick_mismatch")
            if not s["open_count"]:
                attempts+=1
                blocked=D(s["equity"])<START*D(".97")-D(".01") or D(s["drawdown_pct"])>D("10.01")
                try:
                    f.open("BTCUSDT",side)
                    if blocked:violations.append("risk_guard")
                    side="SHORT" if side=="LONG" else "LONG"
                except PaperError:rejected+=1
            s=f.snapshot()
            peak_open=max(peak_open,s["open_count"])
            if D(s["cash"])<0:violations.append("negative_cash")
            if s["open_count"]>1:violations.append("position_limit")
            if s["real_orders"]:violations.append("real_orders")
            curve.append({"tick":i,"equity":s["equity"]})
            if i+1<steps:f.advance()
        for t in f.snapshot()["trades"]:
            if t["exit"] is None:f.close(t["id"])
        s=f.snapshot();trades=s["trades"];reasons=Counter(t["reason"] for t in trades)
        if s["open_count"] or s["equity"]!=s["cash"]:violations.append("cash_reconciliation")
        realized=sum((D(t["pnl"]) for t in trades),D(0))
        if abs(realized-(D(s["equity"])-START))>D(".011"):violations.append("pnl_reconciliation")
        if attempts!=rejected+len(trades):violations.append("entry_reconciliation")
        return {"scenario":scenario,"label":LABELS[scenario],"observations":steps,"mode":"synthetic_stress","market":"FUTURES","currency":"USDT","initial_equity":str(START),"final_equity":s["equity"],"return_pct":str(((D(s["equity"])/START-1)*100).quantize(D(".01"))),"max_recorded_drawdown_pct":s["max_recorded_drawdown_pct"],"closed_trades":len(trades),"stop_exits":reasons["stop"],"target_exits":reasons["target"],"liquidations":reasons["synthetic_liquidation"],"rejected_entries":rejected,"entry_attempts":attempts,"peak_open":peak_open,"invariant_violations":sorted(set(violations)),"passed":not violations,"curve":curve,"real_orders":False,"profitability_verified":False,"promotion_enabled":False,"limits":["Varsayımsal tek oturum, basitleştirilmiş izole teminat ve fonlama."]}
