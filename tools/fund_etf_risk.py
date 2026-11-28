"""Read-only cross-market fund/ETF portfolio risk, one currency at a time."""
import math
import sqlite3
from datetime import date
from pathlib import Path
from statistics import stdev, correlation

CURRENCIES = {"TRY", "USD", "EUR", "GBP"}


def assess(database, holdings, *, currency, cash=0.0, as_of=None,
           min_observations=60, max_age_days=7, max_weight=.25,
           max_group_weight=.60, max_correlation=.85,
           max_drawdown=.20, min_cash_weight=.10, shock=.10):
    """Holdings: market, symbol, source, currency, group, units.

    Group labels must be supplied by the caller. No currency conversion,
    automatic rebalance, actual settlement or order execution.
    """
    as_of = date.fromisoformat(as_of) if as_of else date.today()
    if as_of > date.today() or currency not in CURRENCIES:
        raise ValueError("invalid_date_or_currency")
    if type(min_observations) is not int or min_observations < 60 or type(max_age_days) is not int or max_age_days < 0:
        raise ValueError("invalid_history_policy")
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in
               (max_weight, max_group_weight, max_correlation, max_drawdown, min_cash_weight, shock)):
        raise ValueError("invalid_limits")
    if not math.isfinite(cash) or cash < 0 or not 1 <= len(holdings) <= 100:
        raise ValueError("invalid_portfolio")
    result = {"status": "blocked", "currency": currency, "as_of": as_of.isoformat(),
              "real_orders": False, "execution_allowed": False,
              "live_data_verified": False, "total_return_verified": False,
              "settlement_verified": False, "fx_verified": False}
    identities = set()
    # Multiple price vendors for the same symbol are not independent assets.
    histories = []
    with sqlite3.connect(Path(database).resolve().as_uri()+"?mode=ro", uri=True) as db:
        for h in holdings:
            market, symbol, source, c, group = (h[k] for k in ("market","symbol","source","currency","group"))
            units = h["units"]
            key = (market, symbol)
            if market not in ("ETF","TEFAS") or c != currency or (market=="TEFAS" and c!="TRY"):
                raise ValueError("mixed_or_invalid_currency")
            if not all(isinstance(v,str) and v.strip() and v==v.strip() for v in (symbol, source, group)):
                raise ValueError("invalid_identity_or_group")
            if key in identities or not math.isfinite(units) or units <= 0:
                raise ValueError("duplicate_asset_or_invalid_units")
            identities.add(key)
            rows = db.execute("SELECT session,close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? AND session<=? ORDER BY session",
                              (market,symbol,c,source,as_of.isoformat())).fetchall()
            series = {}
            for session, close in rows:
                day, price = date.fromisoformat(session), float(close)
                if day in series or not math.isfinite(price) or price <= 0 or day > as_of:
                    raise ValueError("invalid_price_series")
                series[day] = price
            if not series or (as_of-max(series)).days > max_age_days:
                return dict(result, reason="missing_or_stale_price", asset=list(key))
            histories.append(series)
    common = sorted(set.intersection(*(set(s) for s in histories)))
    if len(common) < min_observations+1:
        return dict(result, reason="insufficient_common_history", observations=max(0,len(common)-1))
    if (as_of-common[-1]).days > max_age_days:
        return dict(result, reason="stale_common_session")
    # Value all holdings at exactly the same date. Never forward-fill NAV or FX.
    values = [h["units"]*s[common[-1]] for h,s in zip(holdings,histories)]
    equity = cash+sum(values)
    if not math.isfinite(equity) or equity <= 0:
        raise ValueError("invalid_equity")
    weights = [v/equity for v in values]
    group_weights = {}
    market_weights = {}
    positions = []
    for h,v,w in zip(holdings,values,weights):
        group_weights[h["group"]] = group_weights.get(h["group"],0)+w
        market_weights[h["market"]] = market_weights.get(h["market"],0)+w
        positions.append({"market":h["market"],"symbol":h["symbol"],"source":h["source"],
                          "group":h["group"],"value":v,"weight":w})
    series_returns = [[s[b]/s[a]-1 for a,b in zip(common,common[1:])] for s in histories]
    if any(not math.isfinite(v) for row in series_returns for v in row):
        raise ValueError("invalid_returns")
    n = len(holdings)
    matrix = [[None]*n for _ in range(n)]
    pairs = []
    alerts = []
    for i in range(n):
        for j in range(i,n):
            if stdev(series_returns[i]) == 0 or stdev(series_returns[j]) == 0:
                corr = None
            else:
                corr = max(-1.0,min(1.0,correlation(series_returns[i],series_returns[j])))
            matrix[i][j] = matrix[j][i] = corr
            if i != j and (corr is None or corr >= max_correlation):
                pairs.append({"first":i,"second":j,"correlation":corr})
    # Hypothetical constant-current-weight history, not actual account P&L.
    portfolio_returns = [sum(w*r for w,r in zip(weights,obs)) for obs in zip(*series_returns)]
    index, peak, dd = 1.0, 1.0, 0.0
    for r in portfolio_returns:
        index *= 1+r
        if not math.isfinite(index) or index <= 0:
            raise ValueError("invalid_hypothetical_equity")
        peak = max(peak,index)
        dd = max(dd,1-index/peak)
    for p in positions:
        if p["weight"] > max_weight+1e-10:
            alerts.append({"code":"position_limit","market":p["market"],"symbol":p["symbol"]})
    for group,w in group_weights.items():
        if w > max_group_weight+1e-10:
            alerts.append({"code":"group_limit","group":group})
    if pairs:
        alerts.append({"code":"correlation_review","pairs":pairs})
    if dd > max_drawdown:
        alerts.append({"code":"hypothetical_drawdown_limit"})
    if cash/equity+1e-10 < min_cash_weight:
        alerts.append({"code":"cash_floor"})
    return dict(result,status="review_required" if alerts else "research_only",
                equity=equity,cash=cash,cash_weight=cash/equity,
                positions=positions,group_weights=group_weights,market_weights=market_weights,
                observations=len(common)-1,last_session=common[-1].isoformat(),
                correlation_matrix=matrix,correlation_pairs=pairs,
                hypothetical_drawdown=dd,observation_volatility=stdev(portfolio_returns),
                hypothetical_shock_loss=shock*sum(values),
                hypothetical_shock_loss_fraction=shock*sum(weights),
                alerts=alerts,group_labels_verified=False,actual_account_pnl=False,
                limits={"max_weight":max_weight,"max_group_weight":max_group_weight,
                        "max_correlation":max_correlation,"max_drawdown":max_drawdown,
                        "min_cash_weight":min_cash_weight,"shock":shock})


def main():
    import argparse
    import json
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True)
    p.add_argument("--manifest", required=True)
    a = p.parse_args()
    with open(a.manifest, encoding="utf-8") as f:
        manifest = json.load(f)
    report = assess(a.database, **manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 2 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
