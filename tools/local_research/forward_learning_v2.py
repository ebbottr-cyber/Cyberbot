import os
import sys
import json
import math
import time
import sqlite3
import shutil

from pathlib import Path
from collections import defaultdict
from contextlib import closing
from statistics import mean
from datetime import datetime, timezone

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

root = Path(sys.argv[1]).resolve()
cycles = int(sys.argv[2])
if not 1 <= cycles <= 10:
    raise ValueError("Research cycles must be between 1 and 10")

sys.path.insert(0, str(root))

from tools.local_research.vps_guard import MIB, MIN_FREE_DISK_MIB

research_folder = root / "var/ai"
memory = research_folder / "forward-models-v2.sqlite3"


def require_disk_reserve():
    # Check the actual research filesystem, including on Windows.
    # Exit 75 is a deferred research run, not a trading failure.
    free = shutil.disk_usage(research_folder).free
    if free < MIN_FREE_DISK_MIB * MIB:
        print("WAIT_DISK:", free, "bytes free; research paused", flush=True)
        raise SystemExit(75)
    return free


def storage_status():
    sizes = {}
    for suffix in ("", "-wal", "-shm", "-journal"):
        file = Path(str(memory) + suffix)
        try:
            sizes[file.name] = file.stat().st_size
        except FileNotFoundError:
            pass
    return {
        "free_bytes": shutil.disk_usage(research_folder).free,
        "minimum_free_bytes": MIN_FREE_DISK_MIB * MIB,
        "forecast_file_bytes": sizes,
        "forecast_total_bytes": sum(sizes.values()),
        "automatic_deletion": False
    }


if not research_folder.is_dir() or research_folder.is_symlink() or research_folder.parent.is_symlink():
    raise ValueError("Existing local research directory required")
if memory.is_symlink() or (memory.exists() and memory.stat().st_nlink != 1):
    raise ValueError("Unsafe research database path")
require_disk_reserve()

import torch
from chronos import Chronos2Pipeline

from cyberbot.db_paths import pilot_path, checked
from cyberbot.models import fit_predict

torch.set_num_threads(2)

MARKET = "FUTURES"
SYMBOL = "BTCUSDT"
SOURCE = "binance-usdm-public"
CONTEXT = 21
MAX_SCORE_ROWS = 10000

NAMES = (
    "naive",
    "mean",
    "ar1",
    "chronos"
)

def utc():
    return datetime.now(timezone.utc)

def ts(value):
    value = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )
    if value.tzinfo is None:
        raise ValueError("Timezone missing")
    return value.astimezone(timezone.utc)

def minute(value):
    return int(value.timestamp() // 60)

def finite(x):
    return math.isfinite(x)


def current_samples():

    from cyberbot.futures_pilot import VERSION

    source = pilot_path()

    if not source.is_file():
        raise ValueError("Pilot database missing")

    now = utc()
    result = {}

    with closing(sqlite3.connect(
        source.as_uri() + "?mode=ro",
        uri=True,
        timeout=5
    )) as db:

        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")

        account = db.execute(
            "SELECT payload FROM observed_accounts "
            "WHERE market = ?",
            (MARKET,)
        ).fetchone()

        if not account:
            raise ValueError("Futures account missing")

        state = json.loads(account[0])

        if (
            state.get("symbol") != SYMBOL
            or state.get("version") != VERSION
            or (state.get("quote") or {}).get(
                "source"
            ) != SOURCE
        ):
            raise ValueError("Account scope mismatch")

        rows = db.execute(
            "SELECT at, payload "
            "FROM observed_events "
            "WHERE market = ? "
            "AND event = 'observation' "
            "ORDER BY id DESC LIMIT 3000",
            (MARKET,)
        ).fetchall()

    for recorded, payload in rows:

        q = json.loads(payload).get("quote")

        if not isinstance(q, dict):
            continue

        if q.get("source") != SOURCE:
            continue

        expected = {
            "market": MARKET,
            "symbol": SYMBOL,
            "currency": "USDT",
            "contract": "linear_perpetual"
        }

        if any(
            key in q and q[key] != value
            for key, value in expected.items()
        ):
            continue

        at = ts(q["source_at"])
        received = ts(recorded)

        if not at <= received <= now:
            continue

        if (
            at.second < 45
            or (received-at).total_seconds() > 30
        ):
            continue

        bid = float(q["bid"])
        ask = float(q["ask"])

        if not (
            finite(bid)
            and finite(ask)
            and 0 < bid <= ask
        ):
            continue

        key = minute(at)

        if (
            key not in result
            or at > result[key]["at"]
        ):
            result[key] = {
                "at": at,
                "received": received,
                "price": (bid + ask) / 2
            }

    current = minute(now)

    missing = [
        k for k in range(
            current - CONTEXT, current
        )
        if k not in result
    ]

    print(
        "VALID_MINUTE_SAMPLES:", len(result),
        "CONTEXT_READY:", CONTEXT - len(missing),
        "/", CONTEXT,
        flush=True
    )

    if missing:

        print(
            "MISSING_UTC_MINUTES:",
            [
                datetime.fromtimestamp(
                    k * 60,
                    timezone.utc
                ).isoformat()
                for k in missing
            ],
            flush=True
        )

    return result

# Load previously verified local model.

reports = sorted(
    (root / "var/ai").glob("chronos-runtime-*.json")
)

if not reports:
    raise ValueError("Verified Chronos report missing")

runtime = json.loads(
    reports[-1].read_text(encoding="utf-8")
)

if runtime.get("runtime_verified") is not True:
    raise ValueError("Chronos runtime not verified")

model_path = Path(runtime["model_path"])

model = Chronos2Pipeline.from_pretrained(
    str(model_path),
    device_map="cpu",
    local_files_only=True,
    use_safetensors=True,
    trust_remote_code=False
)

print("CHRONOS_LOAD: PASS", flush=True)

# Separate forward-research memory.
# Never write to the paper or pilot databases.

protected = [
    *checked().values(),
    pilot_path()
]

for path in protected:
    if memory.resolve() == path.resolve():
        raise ValueError("Database path collision")
    if memory.exists() and path.exists():
        if memory.samefile(path):
            raise ValueError("Database file collision")

require_disk_reserve()

with closing(sqlite3.connect(
    memory, timeout=5
)) as db:

    db.execute("""
        CREATE TABLE IF NOT EXISTS forecasts (
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            source TEXT NOT NULL,
            target_minute INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            outcome TEXT,
            PRIMARY KEY (
                market,
                symbol,
                source,
                target_minute
            )
        )
    """)

    # Match the scoped pending/settled queries without scanning older statuses.
    db.execute("""
        CREATE INDEX IF NOT EXISTS forecasts_scope_status_target
        ON forecasts (market, symbol, source, status, target_minute)
    """)
    db.commit()

    def settle(samples):

        now_minute = minute(utc())

        pending = db.execute("""
            SELECT target_minute, created_at, payload
            FROM forecasts
            WHERE market = ?
              AND symbol = ?
              AND source = ?
              AND status = 'pending'
              AND target_minute < ?
        """, (
            MARKET, SYMBOL, SOURCE, now_minute
        )).fetchall()

        for target, created, payload in pending:

            sample = samples.get(target)

            if sample is None:

                if now_minute - target < 2:
                    continue

                status = "unmeasurable"
                outcome = {
                    "reason": "missing_target_sample"
                }

            elif sample["at"] <= ts(created):

                status = "unmeasurable"
                outcome = {
                    "reason": "target_not_after_forecast"
                }

            else:

                forecast = json.loads(payload)
                last = forecast["last_price"]

                actual = (
                    sample["price"] / last - 1
                ) * 100

                errors = {
                    name: abs(
                        actual -
                        forecast["predictions"][name]
                    )
                    for name in NAMES
                }

                status = "measured"

                outcome = {
                    "actual_return_pct": actual,
                    "absolute_errors_pct": errors,
                    "target_source_at": (
                        sample["at"].isoformat()
                    ),
                    "interval_covered": (
                        forecast["p10"]
                        <= sample["price"]
                        <= forecast["p90"]
                    ),
                    "execution_verified": False,
                    "real_orders": False
                }

            with db:

                db.execute("""
                    UPDATE forecasts
                    SET status = ?, outcome = ?
                    WHERE market = ?
                      AND symbol = ?
                      AND source = ?
                      AND target_minute = ?
                      AND status = 'pending'
                """, (
                    status,
                    json.dumps(
                        outcome, allow_nan=False
                    ),
                    MARKET, SYMBOL, SOURCE,
                    target
                ))

    def predict(samples):

        now = utc()
        current = minute(now)

        if now.second > 35:
            return "LATE_MINUTE"

        existing = db.execute("""
            SELECT 1 FROM forecasts
            WHERE market = ?
              AND symbol = ?
              AND source = ?
              AND target_minute = ?
        """, (
            MARKET, SYMBOL, SOURCE, current
        )).fetchone()

        if existing:
            return "ALREADY_RECORDED"

        wanted = range(
            current - CONTEXT, current
        )

        if any(k not in samples for k in wanted):
            return "INSUFFICIENT_CONTIGUOUS_DATA"

        if (
            now - samples[current-1]["at"]
        ).total_seconds() > 60:
            return "STALE_CONTEXT"

        past = [
            samples[k]["price"]
            for k in wanted
        ]

        returns = [
            b/a-1
            for a,b in zip(past, past[1:])
        ]

        last = past[-1]

        context = torch.tensor(
            past, dtype=torch.float32
        )

        started = time.monotonic()

        with torch.inference_mode():

            quantiles, points = model.predict_quantiles(
                [context],
                prediction_length=1,
                quantile_levels=[
                    0.1, 0.5, 0.9
                ],
                batch_size=1
            )

        low, mid, high = (
            quantiles[0].reshape(-1).tolist()
        )

        if not (
            all(finite(x) for x in (
                low,mid,high
            ))
            and 0 < low <= mid <= high
        ):
            raise ValueError("Invalid forecast")

        created = utc()

        if (
            minute(created) != current
            or created.second > 35
        ):
            return "FORECAST_WINDOW_EXPIRED"

        payload = {
            "last_price": last,
            "context_bars": CONTEXT,
            "prediction_bars": 1,
            "predictions": {
                "naive": 0.0,
                "mean": mean(returns)*100,
                "ar1": fit_predict(returns)*100,
                "chronos": (mid/last-1)*100
            },
            "p10": low,
            "p50": mid,
            "p90": high,
            "inference_seconds": round(
                time.monotonic()-started, 4
            ),
            "mode": "forward_shadow_research",
            "automatic_promotion": False,
            "real_orders": False
        }

        with db:

            db.execute("""
                INSERT OR IGNORE INTO forecasts
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                MARKET, SYMBOL, SOURCE,
                current, created.isoformat(),
                json.dumps(
                    payload, allow_nan=False
                ),
                "pending", None
            ))

        print(
            "FORECAST:",
            json.dumps(
                payload["predictions"]
            ),
            flush=True
        )

        return "FORECAST_RECORDED"

    def performance():

        measured = db.execute("""
            SELECT outcome FROM forecasts
            WHERE market = ?
              AND symbol = ?
              AND source = ?
              AND status = 'measured'
            ORDER BY target_minute DESC
            LIMIT ?
        """, (
            MARKET, SYMBOL, SOURCE, MAX_SCORE_ROWS
        )).fetchall()

        rows = [
            json.loads(x[0])
            for x in measured
        ]

        counts = dict(db.execute("""
            SELECT status, COUNT(*)
            FROM forecasts
            WHERE market = ?
              AND symbol = ?
              AND source = ?
            GROUP BY status
        """, (
            MARKET, SYMBOL, SOURCE
        )))

        scores = {}

        if rows:

            scores = {
                name: round(mean(
                    x["absolute_errors_pct"][name]
                    for x in rows
                ), 6)
                for name in NAMES
            }

        return {
            "counts": counts,
            "mae_pct": scores,
            "measured_forecasts": len(rows),
            "metrics_window": "latest_measured_forecasts",
            "metrics_window_limit": MAX_SCORE_ROWS,
            "total_measured_forecasts": counts.get("measured", 0),
            "chronos_interval_coverage_pct": (
                round(100*mean(
                    x["interval_covered"]
                    for x in rows
                ),2)
                if rows else None
            ),
            "automatic_model_selection": False,
            "model_weights_updated": False,
            "profitability_verified": False,
            "real_orders": False
        }

    # Run bounded foreground cycles.
    # Align to second 15 of each minute.

    for cycle in range(cycles):

        now = time.time()
        slot = 15 + 60 * math.ceil(
            (now-15)/60
        )

        time.sleep(
            max(0, slot-now)
        )

        require_disk_reserve()
        samples = current_samples()

        settle(samples)
        status = predict(samples)

        print(
            "\nFORWARD_CYCLE:",
            cycle+1, "/", cycles,
            flush=True
        )

        print("STATUS:", status, flush=True)

        print(json.dumps(
            performance(),
            ensure_ascii=True
        ), flush=True)

    require_disk_reserve()
    settle(current_samples())

    result = performance()
    result["storage"] = storage_status()

    result["database_integrity"] = db.execute(
        "PRAGMA quick_check"
    ).fetchone()[0]

    result["created_at"] = utc().isoformat()
    result["model_runtime_verified"] = True
    result["main_engine_modified"] = False

    target = (
        root / "var/ai" /
        ("forward-learning-v2-" +
         utc().strftime("%Y%m%d-%H%M%S-%f")
         + ".json")
    )

    require_disk_reserve()
    target.write_text(
        json.dumps(
            result, indent=2,
            allow_nan=False
        ),
        encoding="utf-8"
    )

    print("\n=== FORWARD LEARNING FINAL STATUS ===")

    print(json.dumps(
        result, indent=2
    ))

    print("MEMORY:", memory)
    print("REPORT:", target)
    print("GEMINI_API_USED: NO")
    print("MODEL_DOWNLOAD: NO")
    print("PILOT_DATABASE_MODIFIED: NO")
    print("AUTO_PROMOTION: OFF")
    print("REAL_ORDERS: OFF")

