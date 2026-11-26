"""Deterministic isolated stress harness using the actual synthetic paper ledger."""
from collections import Counter
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from .market import instrument
from .engine import Ledger, PaperError, START, MAX_OPEN, MAX_DRAWDOWN, DAILY_LOSS, FEE, SLIP

SCENARIOS=("bull","bear","sideways","gap")
LABELS={"bull":"Yükseliş","bear":"Düşüş","sideways":"Yatay","gap":"Ani düşüş / fiyat boşluğu"}
MARKETS=("BIST","NASDAQ","XETRA","SOLANA")

def universe(scenario,steps):
    if scenario not in SCENARIOS or type(steps) is not int or not 60<=steps<=360:
        raise ValueError("Invalid stress scenario or observation count.")
    out={}
    for j,m in enumerate(MARKETS):
        price=D(100); prices=[price]
        for i in range(1,steps):
            wave=D(((i*7+j*3)%11)-5)/1000
            trend={"bull":D(".006"),"bear":D("-.006"),"sideways":D(0),"gap":D(".003")}[scenario]
            change=trend+wave
            if scenario=="gap" and i in (15,steps//2):change=D("-.35")-D(j)/100
            price*=1+change
            prices.append(price)
        v=instrument(m,"STRESS-"+m,prices)
        out[v.symbol]=v
    return out

def run(scenario,steps=240):
    instruments=universe(scenario,steps)
    # Conservative one-session test: no daily risk reset masks a loss.
    with TemporaryDirectory(prefix="cyberbot-stress-") as tmp:
        ledger=Ledger(Path(tmp)/"isolated.sqlite3",instruments=instruments,day_clock=lambda:"2000-01-01")
        rejected=0; attempted=0; violations=[]; peak_open=0; curve=[]; peak=START
        for tick in range(steps):
            snap=ledger.snapshot()
            if tick and snap["tick"]!=tick:violations.append("tick_mismatch")
            active={t["symbol"] for t in snap["trades"] if t["exit"] is None}
            # Fixed repeated entry attempts deliberately pressure the existing risk guard.
            for symbol in instruments:
                if symbol in active:continue
                attempted+=1
                pre=ledger.snapshot()
                blocked=D(pre["equity"])<=START*(1-DAILY_LOSS) or D(pre["drawdown_pct"])>MAX_DRAWDOWN*100+D(".01")
                try:
                    ledger.buy(symbol)
                    # Snapshot uses cents: leave tolerance at the exact rounded threshold.
                    if blocked and D(pre["equity"])<START*(1-DAILY_LOSS)-D(".01"):violations.append("risk_guard")
                except PaperError:
                    rejected+=1
            snap=ledger.snapshot()
            value=D(snap["equity"]);peak=max(peak,value)
            peak_open=max(peak_open,snap["open_count"])
            if D(snap["cash"])<0:violations.append("negative_cash")
            if snap["open_count"]>MAX_OPEN:violations.append("position_limit")
            if len({t["symbol"] for t in snap["trades"] if t["exit"] is None})!=snap["open_count"]:violations.append("duplicate_position")
            if snap["real_orders"]:violations.append("real_orders")
            curve.append({"tick":tick,"equity":str(value)})
            if tick+1<steps:ledger.advance()
        for trade in ledger.snapshot()["trades"]:
            if trade["exit"] is None:ledger.sell(trade["id"])
        snap=ledger.snapshot()
        if snap["open_count"]:violations.append("unclosed_positions")
        if D(snap["equity"])!=D(snap["cash"]):violations.append("cash_reconciliation")
        trades=snap["trades"]
        reasons=Counter(t["reason"] for t in trades)
        realized=sum((D(t["pnl"]) for t in trades),D(0))
        if abs(realized-(D(snap["equity"])-START))>D(".011"):violations.append("pnl_reconciliation")
        return {"scenario":scenario,"label":LABELS[scenario],"observations":steps,"mode":"synthetic_stress",
                "initial_equity":str(START),"final_equity":snap["equity"],"return_pct":snap["return_pct"],
                "max_recorded_drawdown_pct":snap["max_recorded_drawdown_pct"],"closed_trades":len(trades),
                "stop_exits":reasons["stop"],"target_exits":reasons["hedef"],"rejected_entries":rejected,
                "entry_attempts":attempted,"peak_open":peak_open,"invariant_violations":sorted(set(violations)),
                "passed":not violations,"curve":curve,"daily_reset_simulated":False,"real_orders":False,
                "profitability_verified":False,"promotion_enabled":False,
                "limits":["Sentetik ve tek varsayımsal UTC oturumu; gerçek günler değildir.","Ani fiyat boşlukları stop ve zarar eşiklerini aşabilir.","Gözlem bazlı sanal dolum, sabit ücret ve kayma; gerçek likidite, gün içi yol ve gecikme yok."]}

def suite(steps=240):
    return [run(s,steps) for s in SCENARIOS]
