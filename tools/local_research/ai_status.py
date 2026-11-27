"""Read-only research inventory for future PWA integration.

Different evaluation protocols are not comparable leaderboards.
No model promotion, orders, raw price data or external requests.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .adaptive_review import readonly

JOURNALS = {
    "river": ("river-replay-journal.sqlite3", "replay_reports",
              "river-forward-replay-1", "retrospective_prequential"),
    "lightgbm": ("lightgbm-review-journal.sqlite3", "training_reports",
                 "lightgbm-forward-review-1", "retrospective_holdout")
}


def journal_status(folder, name):
    filename, table, version, protocol = JOURNALS[name]
    path = folder/filename
    base = {"protocol":protocol,"comparable_across_protocols":False}
    if not path.is_file():
        return {**base,"status":"NOT_AVAILABLE"}
    try:
        with closing(readonly(path)) as db:
            row = db.execute("SELECT payload FROM "+table+
                             " ORDER BY created_at DESC LIMIT 1").fetchone()
        if row is None:
            return {**base,"status":"NO_REPORT"}
        result = json.loads(row[0])
        if (result["version"] != version
                or result["evidence_status"] != "EXPLORATORY_UNVERIFIED"
                or result["real_orders"] is not False
                or result["automatic_promotion"] is not False):
            raise ValueError("invalid report")
        count = result.get("scored",result.get("test_samples",0))
        if type(count) is not int or count < 0:
            raise ValueError("invalid count")
        return {**base,"status":"RESEARCH_MEASURED" if count and result.get("paired_mae_pct") else "INSUFFICIENT_EVIDENCE",
                "observations_scored":count,"created_at":result.get("created_at"),
                "evidence_status":"EXPLORATORY_UNVERIFIED"}
    except (OSError,sqlite3.Error,ValueError,KeyError,TypeError):
        return {**base,"status":"DATA_REVIEW_REQUIRED"}


def chronos_status(folder):
    path=folder/"forward-models-v2.sqlite3"
    if not path.is_file():
        return {"status":"NOT_AVAILABLE","protocol":"forward_shadow"}
    try:
        with closing(readonly(path)) as db:
            counts=dict(db.execute("""SELECT status,COUNT(*) FROM forecasts
                WHERE market='FUTURES' AND symbol='BTCUSDT' AND source='binance-usdm-public'
                GROUP BY status"""))
        return {"status":"RECORDED_NOT_REVALIDATED","protocol":"forward_shadow",
                "counts":{k:v for k,v in counts.items() if k in ("pending","measured","unmeasurable")}}
    except (OSError,sqlite3.Error):
        return {"status":"DATA_REVIEW_REQUIRED","protocol":"forward_shadow"}


def gemini_status(folder):
    path=folder/"gemini-quota.sqlite3"
    base={"protocol":"generic_advisory","current_market_analysis":False,
          "provider_billing_verified":False}
    if not path.is_file():
        return {**base,"status":"NO_LOCAL_ATTEMPTS"}
    try:
        with closing(readonly(path)) as db:
            row=db.execute("SELECT status FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
        status = row[0] if row else "NO_LOCAL_ATTEMPTS"
        allowed={"OK","RESERVED","PROVIDER_ERROR","NO_LOCAL_ATTEMPTS"}
        if status not in allowed and not (isinstance(status,str) and len(status)==8 and status.startswith("HTTP_") and status[5:].isdigit()):
            raise ValueError("invalid status")
        return {**base,"status":status}
    except (OSError,sqlite3.Error,ValueError):
        return {**base,"status":"DATA_REVIEW_REQUIRED"}


def run(root):
    folder = root/"var/ai"
    return {"version":"ai-status-1","models":{
        "chronos":chronos_status(folder),
        "river":journal_status(folder,"river"),
        "lightgbm":journal_status(folder,"lightgbm"),
        "gemini":gemini_status(folder)},
        "shared_ranking_available":False,"automatic_promotion":False,
        "profitability_verified":False,"real_orders":False}


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    print(json.dumps(run(p.parse_args().root.resolve()),indent=2,allow_nan=False))
