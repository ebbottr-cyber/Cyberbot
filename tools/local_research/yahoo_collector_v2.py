import sys
import json
import math
import time
import sqlite3

from pathlib import Path
from datetime import datetime, timezone, timedelta
from contextlib import closing
from statistics import mean

import yfinance as yf

yf.config.debug.hide_exceptions = False

ROOT = Path.cwd()
FOLDER = ROOT / "var/providers"
DATABASE = FOLDER / "yahoo-equity5m-v1.sqlite3"

MARKETS = {
    "BIST": [
        "THYAO.IS",
        "ASELS.IS",
        "GARAN.IS"
    ],
    "NASDAQ": [
        "AAPL",
        "MSFT",
        "NVDA"
    ],
    "XETRA": [
        "SAP.DE",
        "SIE.DE",
        "ALV.DE"
    ]
}

def utc():
    return datetime.now(timezone.utc)

def stamp():
    return utc().strftime("%Y%m%d-%H%M%S-%f")

def valid(values):

    o,h,l,c,v = values

    return (
        all(math.isfinite(x) for x in values)
        and 0 < l <= min(o,c)
        and h >= max(o,c)
        and v >= 0
    )

if not DATABASE.is_file():
    raise SystemExit("Existing Yahoo database missing")

if "--collect" not in sys.argv:
    raise SystemExit("Explicit --collect required")

backup = FOLDER / (
    "yahoo-backup-" + stamp() + ".sqlite3"
)

results = []
stopped = False

with closing(sqlite3.connect(
    DATABASE, timeout=10
)) as db:

    if db.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0] != "ok":
        raise ValueError("Source database integrity")

    with closing(sqlite3.connect(backup)) as dst:

        db.backup(dst)

        if dst.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] != "ok":
            raise ValueError("Backup integrity")

    print("DATABASE_BACKUP: PASS")
    print("BACKUP:", backup)

    before = db.execute(
        "SELECT COUNT(*) FROM candles_5m"
    ).fetchone()[0]

    for market, symbols in MARKETS.items():

        for ticker in symbols:

            if stopped:
                break

            print(
                "\nMARKET:", market,
                "SYMBOL:", ticker,
                flush=True
            )

            result = {
                "market": market,
                "symbol": ticker,
                "status": "FAILED"
            }

            try:

                data = yf.Ticker(ticker).history(
                    period="5d",
                    interval="5m",
                    auto_adjust=False,
                    actions=False,
                    prepost=False,
                    timeout=20
                )

                if data.empty:
                    raise ValueError("No data")

                if data.index.tz is None:
                    raise ValueError("Missing timezone")

                data.index = data.index.tz_convert("UTC")

                if (
                    data.index.has_duplicates
                    or not data.index.is_monotonic_increasing
                ):
                    raise ValueError("Invalid timestamps")

                now = utc()
                cutoff = now - timedelta(minutes=20)

                new = duplicates = conflicts = 0
                invalid = recent = zero = 0

                with db:

                    for index,row in data.iterrows():

                        at = index.to_pydatetime()

                        if (
                            at > now
                            or at.minute % 5
                            or at.second
                            or at.microsecond
                        ):
                            invalid += 1
                            continue

                        if at > cutoff:
                            recent += 1
                            continue

                        values = tuple(
                            float(row[k])
                            for k in (
                                "Open","High","Low",
                                "Close","Volume"
                            )
                        )

                        if not valid(values):
                            invalid += 1
                            continue

                        if values[4] == 0:
                            zero += 1

                        key = (
                            market,ticker,at.isoformat()
                        )

                        old = db.execute("""
                            SELECT open,high,low,
                                   close,volume
                            FROM candles_5m
                            WHERE market=?
                              AND ticker=?
                              AND ts_utc=?
                        """, key).fetchone()

                        if old is not None:

                            if tuple(old) == values:
                                duplicates += 1
                            else:
                                conflicts += 1

                            continue

                        db.execute("""
                            INSERT INTO candles_5m
                            VALUES (?,?,?,?,?,?,?,?,?)
                        """, (
                            *key,*values,
                            now.isoformat()
                        ))

                        new += 1

                    count = db.execute("""
                        SELECT COUNT(*)
                        FROM candles_5m
                        WHERE market=? AND ticker=?
                    """, (
                        market,ticker
                    )).fetchone()[0]

                    result.update({
                        "status": (
                            "REVIEW_REQUIRED"
                            if invalid or conflicts or not count
                            else "PASS"
                        ),
                        "new_rows": new,
                        "duplicates": duplicates,
                        "conflicts": conflicts,
                        "invalid_rows": invalid,
                        "recent_excluded": recent,
                        "zero_volume": zero,
                        "total_saved": count,
                        "research_only": True,
                        "realtime_verified": False,
                        "venue_verified": False
                    })

                    db.execute("""
                        INSERT INTO collection_runs
                        (
                            collected_at,
                            market,
                            ticker,
                            summary
                        )
                        VALUES (?,?,?,?)
                    """, (
                        now.isoformat(),
                        market,ticker,
                        json.dumps(result,allow_nan=False)
                    ))

            except Exception as exc:

                result.update({
                    "status": "FAILED",
                    "error_type": type(exc).__name__
                })

                if (
                    "RateLimit" in type(exc).__name__
                    or "429" in str(exc)
                ):
                    stopped = True

            results.append(result)

            print(
                json.dumps(result,ensure_ascii=True),
                flush=True
            )

            if stopped:
                print("RATE_LIMIT_STOP")
                break

            time.sleep(5)

    inventory = []

    for market,symbols,bars,positive in db.execute("""
        SELECT market,
               COUNT(DISTINCT ticker),
               COUNT(*),
               SUM(CASE WHEN volume>0 THEN 1 ELSE 0 END)
        FROM candles_5m
        GROUP BY market
    """):

        inventory.append({
            "market": market,
            "symbols": symbols,
            "candles": bars,
            "positive_volume": positive
        })

    after = db.execute(
        "SELECT COUNT(*) FROM candles_5m"
    ).fetchone()[0]

    integrity = db.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    repeated_keys = db.execute("""
        SELECT COUNT(*) FROM (
            SELECT market,ticker,ts_utc
            FROM candles_5m
            GROUP BY market,ticker,ts_utc
            HAVING COUNT(*)>1
        )
    """).fetchone()[0]

inserted = sum(
    x.get("new_rows",0) for x in results
)

dedup = sum(
    x.get("duplicates",0) for x in results
)

conflicts = sum(
    x.get("conflicts",0) for x in results
)

report = {
    "created_at": utc().isoformat(),
    "provider": "yfinance",
    "version": yf.__version__,
    "requested_symbols": 9,
    "attempted_symbols": len(results),
    "passed_symbols": sum(
        x["status"]=="PASS" for x in results
    ),
    "inventory": inventory,
    "candles_before": before,
    "candles_after": after,
    "new_candles": inserted,
    "duplicates_skipped": dedup,
    "revision_conflicts": conflicts,
    "duplicate_keys": repeated_keys,
    "row_accounting_ok": after-before == inserted,
    "database_integrity": integrity,
    "rate_limit_stop": stopped,
    "results": results,
    "research_only": True,
    "realtime_verified": False,
    "venue_verified": False,
    "auto_promotion": False,
    "real_orders": False
}

target = FOLDER / (
    "yahoo-v2-collection-" + stamp() + ".json"
)

with target.open("x",encoding="utf-8") as f:
    json.dump(
        report,f,indent=2,allow_nan=False
    )

print("\n=== YAHOO V2 FINAL STATUS ===")

for item in inventory:
    print(json.dumps(item))

print("REQUESTED_SYMBOLS: 9")
print("ATTEMPTED_SYMBOLS:", len(results))
print("PASSED_SYMBOLS:", report["passed_symbols"])
print("CANDLES_BEFORE:", before)
print("NEW_CANDLES:", inserted)
print("CANDLES_AFTER:", after)
print("DUPLICATES_SKIPPED:", dedup)
print("REVISION_CONFLICTS:", conflicts)
print("DUPLICATE_KEYS:", repeated_keys)
print("ROW_ACCOUNTING_OK:", after-before == inserted)
print("DATABASE_INTEGRITY:", integrity)
print("RATE_LIMIT_STOP:", stopped)
print("REPORT:", target)
print("REAL_ORDERS: OFF")

ok = (
    integrity=="ok"
    and repeated_keys==0
    and after-before==inserted
    and len(results)==9
    and report["passed_symbols"]==9
)

raise SystemExit(0 if ok else 1)

