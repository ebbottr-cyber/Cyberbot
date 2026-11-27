import os
import sys
import csv
import json
import math
import sqlite3

from pathlib import Path
from statistics import mean
from contextlib import closing
from datetime import datetime, timezone
from collections import defaultdict

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

root = Path.cwd()
sys.path.insert(0, str(root))

import torch
from chronos import Chronos2Pipeline
from cyberbot.models import fit_predict

torch.set_num_threads(2)

archive = Path(os.environ["CYBERBOT_EQUITY_ARCHIVE"]).expanduser().resolve()

yahoo = (
    root / "var/providers/yahoo-equity5m-v1.sqlite3"
)

folder = root / "var/research5m"
folder.mkdir(parents=True, exist_ok=True)

stamp = datetime.now(timezone.utc).strftime(
    "%Y%m%d-%H%M%S-%f"
)

def readonly(path):
    if not path.is_file():
        raise ValueError("Database missing: " + str(path))

    return sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=10
    )

print("\n=== FULL EQUITY INVENTORY ===")

with closing(readonly(archive)) as db:

    db.execute("PRAGMA query_only=ON")

    inventory = db.execute("""
        SELECT market,ticker,
               COUNT(*),
               SUM(CASE WHEN volume>0
                        THEN 1 ELSE 0 END),
               COUNT(DISTINCT SUBSTR(ts_utc,1,10)),
               MIN(ts_utc),
               MAX(ts_utc)
        FROM candles_5m
        WHERE market IN ('BIST','NASDAQ','XETRA')
        GROUP BY market,ticker
        ORDER BY market,ticker
    """).fetchall()

inventory_file = folder / (
    "equity-universe-" + stamp + ".csv"
)

with inventory_file.open(
    "x", encoding="utf-8-sig", newline=""
) as f:

    writer = csv.writer(f)

    writer.writerow([
        "market","ticker","candles",
        "positive_volume_candles",
        "days","first_utc","last_utc",
        "minimum_history_pass"
    ])

    for row in inventory:
        writer.writerow([
            *row, row[3]>=240 and row[4]>=3
        ])

coverage = {}

for market in ("BIST","NASDAQ","XETRA"):

    rows = [r for r in inventory if r[0]==market]

    eligible = [
        r for r in rows
        if r[3]>=240 and r[4]>=3
    ]

    coverage[market] = {
        "symbols": len(rows),
        "candles": sum(r[2] for r in rows),
        "minimum_history_pass": len(eligible)
    }

    print(market, json.dumps(coverage[market]))

print("TOTAL_SYMBOLS:", len(inventory))
print("INVENTORY:", inventory_file)

print("\n=== CHRONOS LOAD ===")

reports = sorted(
    (root / "var/ai").glob("chronos-runtime-*.json")
)

if not reports:
    raise ValueError("Chronos runtime report missing")

runtime = json.loads(
    reports[-1].read_text(encoding="utf-8")
)

model_path = Path(runtime["model_path"])

model = Chronos2Pipeline.from_pretrained(
    str(model_path),
    device_map="cpu",
    local_files_only=True,
    use_safetensors=True,
    trust_remote_code=False
)

print("CHRONOS_LOAD: PASS")

print("\n=== YAHOO EQUITY AI RESEARCH ===")

with closing(readonly(yahoo)) as db:

    db.execute("PRAGMA query_only=ON")

    rows = db.execute("""
        SELECT market,ticker,ts_utc,
               close,volume
        FROM candles_5m
        ORDER BY market,ticker,ts_utc
    """).fetchall()

groups = defaultdict(list)

for market,ticker,at,price,volume in rows:

    dt = datetime.fromisoformat(at)

    groups[(market,ticker,dt.date())].append(
        (dt,float(price),float(volume))
    )

names = ("naive","mean","ar1","chronos")
scores = defaultdict(list)
details = []

for key,bars in sorted(groups.items()):

    market,ticker,day = key

    # 60 prior candles and one future target.
    # No crossing UTC days or missing intervals.

    for i in range(60,len(bars),5):

        window = bars[i-60:i+1]

        if any(
            not math.isfinite(price)
            or price<=0
            or not math.isfinite(volume)
            or volume<=0
            for _,price,volume in window
        ):
            continue

        if any(
            (b[0]-a[0]).total_seconds()!=300
            for a,b in zip(window,window[1:])
        ):
            continue

        past = [r[1] for r in window[:-1]]
        target = window[-1][1]
        last = past[-1]

        returns = [
            b/a-1 for a,b in zip(past,past[1:])
        ]

        with torch.inference_mode():

            q,_ = model.predict_quantiles(
                [torch.tensor(
                    past,dtype=torch.float32
                )],
                prediction_length=1,
                quantile_levels=[0.1,0.5,0.9],
                batch_size=1
            )

        low,mid,high = q[0].reshape(-1).tolist()

        if not (
            all(math.isfinite(x)
                for x in (low,mid,high))
            and 0<low<=mid<=high
        ):
            raise ValueError("Invalid model output")

        actual = (target/last-1)*100

        forecasts = {
            "naive": 0.0,
            "mean": mean(returns)*100,
            "ar1": fit_predict(returns)*100,
            "chronos": (mid/last-1)*100
        }

        errors = {
            name: abs(actual-forecasts[name])
            for name in names
        }

        item = {
            "market": market,
            "ticker": ticker,
            "target_at": window[-1][0].isoformat(),
            "absolute_errors_pct": errors,
            "chronos_interval_covered": low<=target<=high
        }

        scores[market].append(item)
        details.append(item)

performance = {}

for market in ("BIST","NASDAQ","XETRA"):

    samples = scores[market]

    if not samples:
        performance[market] = {
            "status":"INSUFFICIENT_DATA"
        }
        continue

    errors = {
        name: round(mean(
            row["absolute_errors_pct"][name]
            for row in samples
        ),6)
        for name in names
    }

    performance[market] = {
        "status":"MEASURED",
        "forecasts":len(samples),
        "symbols":len({
            r["ticker"] for r in samples
        }),
        "mae_pct":errors,
        "chronos_coverage_pct":round(
            100*mean(
                r["chronos_interval_covered"]
                for r in samples
            ),2
        )
    }

    print(market,json.dumps(performance[market]))

report = {
    "created_at":datetime.now(timezone.utc).isoformat(),
    "inventory":coverage,
    "performance":performance,
    "total_forecasts":len(details),
    "context_candles":60,
    "forecast_horizon_minutes":5,
    "model_path":str(model_path),
    "source":"local Yahoo research archive",
    "evidence_status":"EXPLORATORY_UNVERIFIED",
    "independent_validation":False,
    "model_weights_updated":False,
    "automatic_model_selection":False,
    "profitability_verified":False,
    "real_orders":False,
    "measurements":details
}

target = folder / (
    "yahoo-equity-ai-" + stamp + ".json"
)

with target.open("x",encoding="utf-8") as f:
    json.dump(
        report,f,indent=2,allow_nan=False
    )

print("\n=== EQUITY AI FINAL STATUS ===")
print("INVENTORY_SYMBOLS:",len(inventory))
print("TOTAL_FORECASTS:",len(details))
print("PERFORMANCE:",json.dumps(performance))
print("REPORT:",target)
print("YAHOO_NETWORK_REQUESTS: NO")
print("GEMINI_API_USED: NO")
print("SOURCE_DATABASES_MODIFIED: NO")
print("AUTO_PROMOTION: OFF")
print("REAL_ORDERS: OFF")

