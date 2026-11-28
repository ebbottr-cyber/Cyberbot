"""Walk-forward price-only strategy evaluation; offline research, never orders."""
import argparse
import json
import math
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

# Fixed candidate universe; changing it after seeing results invalidates holdout evidence.
STRATEGIES = {"momentum_20": ("momentum", 20), "momentum_60": ("momentum", 60),
              "sma_20": ("sma", 20), "sma_60": ("sma", 60), "cash": ("cash", 0)}
WARMUP = 60


def signal(prices, j, strategy):
    kind, n = STRATEGIES[strategy]
    if kind == "cash":
        return False
    if j < n:
        return False
    if kind == "momentum":
        return prices[j] > prices[j-n]
    return prices[j] > sum(prices[j-n+1:j+1])/n


def simulate(prices, start, stop, strategy, cost_bps, lag):
    """Independent fold, unit starting capital, predetermined final liquidation."""
    cash, units, peak, dd, fees, trades = 1.0, 0.0, 1.0, 0.0, 0.0, 0
    rate = cost_bps/10000
    for i in range(start, stop):
        p = prices[i]
        # Final close is a precommitted liquidation, not a signal-dependent fill.
        target = i < stop-1 and (strategy == "buy_hold" or signal(prices, i-lag, strategy))
        if target and not units:
            fee = cash*rate/(1+rate)
            units, cash = (cash-fee)/p, 0.0
            fees += fee
            trades += 1
        elif not target and units:
            gross = units*p
            fee = gross*rate
            cash, units = gross-fee, 0.0
            fees += fee
            trades += 1
        equity = cash+units*p
        peak = max(peak, equity)
        dd = max(dd, 1-equity/peak)
    return {"return_pct": 100*(cash-1), "max_drawdown_pct": 100*dd,
            "trades": trades, "fees_pct_initial": 100*fees}


def evaluate(rows, *, train=252, test=63, lag=1, cost_bps=25.0, risk_penalty=1.0):
    if any(type(n) is not int for n in (train, test, lag)) or train < 60 or test < 2 or lag < 1:
        raise ValueError("invalid_window_or_lag")
    if not math.isfinite(cost_bps) or not 0 <= cost_bps < 5000:
        raise ValueError("invalid_cost")
    if not math.isfinite(risk_penalty) or risk_penalty < 0:
        raise ValueError("invalid_risk_penalty")
    days = [date.fromisoformat(r[0]) for r in rows]
    prices = [float(r[1]) for r in rows]
    if days != sorted(set(days)) or any(d > date.today() for d in days):
        raise ValueError("invalid_sessions")
    if any(not math.isfinite(p) or p <= 0 for p in prices):
        raise ValueError("invalid_prices")
    first = WARMUP+lag+train
    folds = []
    for start in range(first, len(prices)-test+1, test):
        stop = start+test
        training = {name: simulate(prices, start-train, start, name, cost_bps, lag)
                    for name in STRATEGIES}
        # Selection never uses test observations; cash wins exact ties.
        def rank(name):
            m = training[name]
            return (-(m["return_pct"]-risk_penalty*m["max_drawdown_pct"]),
                    name != "cash", name)
        selected = min(training, key=rank)
        candidates = {name: simulate(prices, start, stop, name, cost_bps, lag)
                      for name in STRATEGIES}
        benchmark = simulate(prices, start, stop, "buy_hold", cost_bps, lag)
        stress = simulate(prices, start, stop, selected, 2*cost_bps, lag)
        folds.append({"train_start": days[start-train].isoformat(),
                      "train_end": days[start-1].isoformat(),
                      "test_start": days[start].isoformat(),
                      "test_end": days[stop-1].isoformat(),
                      "selected": selected, "training": training,
                      "test": candidates[selected], "candidate_tests": candidates,
                      "benchmark": benchmark, "stress": stress})
    result = {"status": "offline_research" if len(folds) >= 3 else "insufficient_evaluation",
              "fold_count": len(folds), "folds": folds, "cost_bps": cost_bps,
              "stress_cost_bps": 2*cost_bps, "lag_observations": lag,
              "train_observations": train, "test_observations": test,
              "risk_penalty": risk_penalty, "model_promoted": False,
              "real_orders": False, "settlement_verified": False,
              "total_return_verified": False, "live_data_verified": False}
    if folds:
        def aggregate(key):
            metrics = [f[key] for f in folds]
            return {"chained_return_pct": 100*(math.prod(1+m["return_pct"]/100 for m in metrics)-1),
                    "worst_fold_drawdown_pct": max(m["max_drawdown_pct"] for m in metrics),
                    "positive_folds": sum(m["return_pct"] > 0 for m in metrics),
                    "trades": sum(m["trades"] for m in metrics)}
        result["summary"] = {key: aggregate(key) for key in ("test", "benchmark", "stress")}
        result["summary"]["selection_counts"] = {
            name: sum(f["selected"] == name for f in folds) for name in STRATEGIES}
    return result


def from_archive(database, market, symbol, currency, source, **policy):
    if market not in ("ETF", "TEFAS"):
        raise ValueError("invalid_market")
    path = Path(database).resolve()
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as db, db:
        rows = db.execute("SELECT session,close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? ORDER BY session",
                          (market, symbol, currency, source)).fetchall()
    return dict(evaluate(rows, **policy), market=market, symbol=symbol,
                currency=currency, source=source)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("database", "market", "symbol", "currency", "source"):
        p.add_argument("--"+arg, required=True)
    p.add_argument("--train", type=int, default=252)
    p.add_argument("--test", type=int, default=63)
    p.add_argument("--lag", type=int, default=1)
    p.add_argument("--cost-bps", type=float, default=25)
    p.add_argument("--risk-penalty", type=float, default=1)
    args = vars(p.parse_args())
    print(json.dumps(from_archive(**args), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
