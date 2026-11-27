"""Offline, read-only equity universe evaluation. No network or execution."""
import argparse
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timezone
from itertools import groupby
import json
import math
from pathlib import Path
from statistics import mean
import sqlite3

from cyberbot.models import fit_predict

MARKETS = ("BIST", "NASDAQ", "XETRA")
MODELS = ("naive", "mean", "ar1")
CONTEXT = 61


def read_only(path):
    path = Path(path).resolve(strict=True)
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    return db


def parse_bar(row, interval):
    stamp, o, h, l, c, v = row
    if any(type(x) not in (float, int) or not math.isfinite(x)
           for x in (o, h, l, c, v)):
        return None
    if not (0 < l <= min(o, c) <= max(o, c) <= h and v > 0):
        return None
    try:
        if interval == "5m":
            t = datetime.fromisoformat(stamp)
            if t.utcoffset() is None or t.utcoffset().total_seconds() != 0:
                return None
            if t.minute % 5 or t.second or t.microsecond:
                return None
            if t >= datetime.now(timezone.utc):
                return None
        else:
            t = date.fromisoformat(stamp)
            if t >= datetime.now(timezone.utc).date():
                return None
    except (TypeError, ValueError):
        return None
    return t, c


def adjacent(a, b, interval):
    if interval == "5m":
        return a.date() == b.date() and (b-a).total_seconds() == 300
    return 1 <= (b-a).days <= 7


def evaluate(rows, interval):
    # Fixed models; no parameter selection from target outcomes.
    history = []
    totals = dict.fromkeys(MODELS, 0.0)
    measured = invalid = valid = breaks = 0
    previous = None
    for row in rows:
        bar = parse_bar(row, interval)
        if bar is None:
            invalid += 1
            history.clear()
            previous = None
            continue
        t, c = bar
        valid += 1
        if previous is not None and not adjacent(previous, t, interval):
            history.clear()
            breaks += 1
        previous = t
        if len(history) == CONTEXT:
            past = [b/a-1 for a, b in zip(history, history[1:])]
            actual = c/history[-1]-1
            if all(abs(r) <= 10 for r in past) and abs(actual) <= 10:
                predictions = (0.0, mean(past), fit_predict(past))
                for name, prediction in zip(MODELS, predictions):
                    totals[name] += abs(actual-prediction)*100
                measured += 1
            else:
                history.clear()
        history.append(c)
        history = history[-CONTEXT:]
    return {"valid": valid, "invalid_or_zero_volume": invalid,
            "discontinuities": breaks, "measured": measured,
            "absolute_error_sums_pct": totals}


def empty():
    return {"symbols_seen": 0, "symbols_measured": 0, "valid": 0,
            "invalid_or_zero_volume": 0, "discontinuities": 0,
            "measured": 0, "absolute_error_sums_pct": dict.fromkeys(MODELS, 0.0)}


def add(bucket, result):
    bucket["symbols_seen"] += 1
    bucket["symbols_measured"] += int(result["measured"] > 0)
    for key in ("valid", "invalid_or_zero_volume", "discontinuities", "measured"):
        bucket[key] += result[key]
    for name in MODELS:
        bucket["absolute_error_sums_pct"][name] += result["absolute_error_sums_pct"][name]


def summary(buckets):
    for bucket in buckets.values():
        n = bucket["measured"]
        bucket["mae_pct"] = {k: round(v/n, 8) for k, v in
                             bucket.pop("absolute_error_sums_pct").items()} if n else None
        bucket.pop("absolute_error_sums_pct", None)
    return buckets


def run(root):
    base = root / "var/providers"
    keys = defaultdict(set)
    intraday = {m: empty() for m in MARKETS}
    daily = {m: empty() for m in (*MARKETS, "UNMATCHED")}
    with closing(read_only(base / "equity-full-local-5m.sqlite3")) as db:
        cursor = db.execute("""
            SELECT market,ticker,ts_utc,open,high,low,close,volume
            FROM candles_5m WHERE market IN ('BIST','NASDAQ','XETRA')
            ORDER BY market,ticker,ts_utc
        """)
        for (market, ticker), rows in groupby(cursor, lambda r: r[:2]):
            keys[ticker].add(market)
            add(intraday[market], evaluate((r[2:] for r in rows), "5m"))
    with closing(read_only(base / "equity-full-local-1d.sqlite3")) as db:
        cursor = db.execute("""
            SELECT code,date,open,high,low,close,volume
            FROM stock_daily ORDER BY code,date
        """)
        for ticker, rows in groupby(cursor, lambda r: r[0]):
            matches = keys.get(ticker, set())
            market = next(iter(matches)) if len(matches) == 1 else "UNMATCHED"
            add(daily[market], evaluate((r[1:] for r in rows), "1d"))
    return {"created_at": datetime.now(timezone.utc).isoformat(),
            "5m": summary(intraday), "1d": summary(daily),
            "daily_mapping": "exact unique symbol match to 5m universe; unmatched separate",
            "daily_horizon": "next observed date, not verified exchange session",
            "context_prices": CONTEXT, "evidence_status": "EXPLORATORY_UNVERIFIED",
            "overlapping_windows": True, "license_verified": False,
            "chronos_evaluated": False, "weights_updated": False,
            "automatic_model_selection": False, "profitability_verified": False,
            "network_download": False, "real_orders": False}


def self_test():
    from datetime import timedelta
    start = datetime(2020, 1, 2, 8, tzinfo=timezone.utc)
    rows = [((start+timedelta(minutes=5*i)).isoformat(),
             100, 100, 100, 100, 1) for i in range(63)]
    result = evaluate(rows, "5m")
    assert result["measured"] == 2
    assert all(v == 0 for v in result["absolute_error_sums_pct"].values())
    assert evaluate(rows[:61], "5m")["measured"] == 0
    broken = list(rows)
    broken[30] = (*broken[30][:-1], 0)
    assert evaluate(broken, "5m")["measured"] == 0
    assert evaluate(broken, "5m")["invalid_or_zero_volume"] == 1
    assert not adjacent(start, start+timedelta(minutes=10), "5m")
    assert not adjacent(start, start+timedelta(days=1), "5m")
    print("SELF_TEST: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.run:
        root = Path(__file__).resolve().parents[2]
        report = run(root)
        folder = root / "var/research5m"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        target = folder / ("full-universe-baselines-" + stamp + ".json")
        with target.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
        print(json.dumps(report, indent=2, allow_nan=False))
        print("REPORT:", target)
    if not (args.self_test or args.run):
        parser.error("choose --self-test or --run")


if __name__ == "__main__":
    main()
