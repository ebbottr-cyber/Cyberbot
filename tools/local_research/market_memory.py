"""Market-isolated aggregate research memory; never a trading database."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3

from .adaptive_review import readonly
from cyberbot.db_paths import checked, pilot_path, same

MARKETS = ("BIST", "NASDAQ", "XETRA", "FUTURES", "SOLANA")
INTERVALS = {"BIST":("5m","1d"),"NASDAQ":("5m","1d"),"XETRA":("5m","1d"),
             "FUTURES":("1m","5m"),"SOLANA":("1m","5m")}
EVIDENCE = "EXPLORATORY_UNVERIFIED"
VERSION = "market-memory-1"


def scope(market, symbol, interval, source, protocol):
    if market not in INTERVALS or interval not in INTERVALS[market]:
        raise ValueError("invalid market interval")
    if not isinstance(symbol,str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}",symbol):
        raise ValueError("invalid symbol")
    if market == "SOLANA":
        alphabet="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}",symbol):
            raise ValueError("Solana mint required")
        value=0
        for ch in symbol:
            value=value*58+alphabet.index(ch)
        size=(value.bit_length()+7)//8+len(symbol)-len(symbol.lstrip("1"))
        if size!=32:
            raise ValueError("invalid Solana mint length")
    for value in (source,protocol):
        if not isinstance(value,str) or not re.fullmatch(r"[a-z0-9_-]{1,80}",value):
            raise ValueError("invalid scope identifier")
    if symbol == "UNIVERSE" and market not in MARKETS[:3]:
        raise ValueError("universe scope is equity-only")
    return market,symbol,interval,source,protocol


def record(key, fingerprint, measured, scores, created):
    if key != scope(*key):
        raise ValueError("invalid scope")
    if not isinstance(fingerprint,str) or not re.fullmatch(r"[0-9a-f]{64}",fingerprint):
        raise ValueError("invalid fingerprint")
    if type(measured) is not int or measured<0:
        raise ValueError("invalid sample count")
    if not isinstance(scores,dict) or (not measured and scores) or (measured and not scores):
        raise ValueError("invalid score availability")
    if not set(scores)<={"naive","mean","ar1","chronos","lightgbm","river"}:
        raise ValueError("unknown model")
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in scores.values()):
        raise ValueError("invalid score")
    t=datetime.fromisoformat(created.replace("Z","+00:00"))
    if t.tzinfo is None or t>datetime.now(timezone.utc):
        raise ValueError("invalid report time")
    created=t.astimezone(timezone.utc).isoformat()
    return (*key,fingerprint,created,measured,json.dumps(scores,sort_keys=True,allow_nan=False),EVIDENCE)


def equity_records(payload, fingerprint):
    if (payload["evidence_status"]!=EVIDENCE or payload["real_orders"] is not False
            or payload["automatic_model_selection"] is not False
            or payload["profitability_verified"] is not False
            or payload["license_verified"] is not False):
        raise ValueError("unsafe archive report")
    for market in MARKETS[:3]:
        for interval in INTERVALS[market]:
            b=payload[interval][market]
            n=b["measured"]
            yield record(scope(market,"UNIVERSE",interval,"local_equity_archive",
                        "historical_overlapping_baseline"),fingerprint,n,
                        b["mae_pct"] if n else {},payload["created_at"])


def paired_record(payload, fingerprint):
    if (payload["version"]!="paired-ai-review-1"
            or payload["market"]!="FUTURES" or payload["symbol"]!="BTCUSDT"
            or payload["interval"]!="1m" or payload["source"]!="binance-usdm-public"
            or payload["evidence_status"]!=EVIDENCE
            or payload["comparison_protocol"]!="same_targets_frozen_batch_online_replay"
            or payload["automatic_promotion"] is not False
            or payload["live_prediction_verified"] is not False
            or payload["real_orders"] is not False):
        raise ValueError("invalid paired source")
    measured=payload["status"]=="RESEARCH_MEASURED"
    if not measured and payload["status"]!="INSUFFICIENT_EVIDENCE":
        raise ValueError("invalid paired status")
    scores=payload["daily_weighted_mae_pct"] if measured else {}
    if measured and (set(scores)!={"naive","mean","ar1","chronos","lightgbm","river"}
                     or payload["test_samples"]<20 or payload["train_samples"]<60):
        raise ValueError("incomplete paired evidence")
    return record(scope("FUTURES","BTCUSDT","1m","binance-usdm-public",
                        "paired_retrospective"),fingerprint,
                  payload["test_samples"] if measured else 0,scores,payload["created_at"])


def path_for(root, market):
    if market not in MARKETS:
        raise ValueError("invalid market")
    return root/"var/ai/market-memory"/(market.lower()+".sqlite3")


def save(root, records):
    if os.environ.get("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("research rights confirmation required")
    protected=[*checked().values(),pilot_path(),
               *checked(root/"var/paper.sqlite3").values(),pilot_path(root/"var/paper.sqlite3")]
    protected += [root/"var/learning.sqlite3",root/"var/ai/forward-models-v2.sqlite3",
                  root/"var/ai/paired-ai-review.sqlite3"]
    paths=[path_for(root,m) for m in MARKETS]
    for p in paths:
        if p.is_symlink() or (p.exists() and p.stat().st_nlink!=1) or any(same(p.resolve(),q.resolve()) for q in protected):
            raise ValueError("unsafe memory path")
    groups={m:[] for m in MARKETS}
    for row in records:
        market,symbol,interval,source,protocol,fingerprint,created,n,scores,evidence=row
        if evidence!=EVIDENCE:
            raise ValueError("invalid evidence")
        groups[market].append(record(scope(market,symbol,interval,source,protocol),
                                     fingerprint,n,json.loads(scores),created))
    for market,rows in groups.items():
        path=path_for(root,market)
        path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(path,timeout=10)) as db,db:
            db.execute("""CREATE TABLE IF NOT EXISTS reports (
                market TEXT NOT NULL,symbol TEXT NOT NULL,interval TEXT NOT NULL,
                source TEXT NOT NULL,protocol TEXT NOT NULL,fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,measured INTEGER NOT NULL,scores TEXT NOT NULL,
                evidence TEXT NOT NULL,
                PRIMARY KEY(market,symbol,interval,source,protocol,fingerprint)
            )""")
            db.executemany("INSERT OR IGNORE INTO reports VALUES (?,?,?,?,?,?,?,?,?,?)",rows)
            if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                raise RuntimeError("memory integrity failed")


def inventory(root):
    result={}
    for market in MARKETS:
        path=path_for(root,market)
        if not path.is_file():
            result[market]={"status":"NOT_INITIALIZED","scopes":[]}
            continue
        try:
            with closing(readonly(path)) as db:
                if db.execute("SELECT COUNT(*) FROM reports WHERE market<>?",(market,)).fetchone()[0]:
                    raise ValueError("cross-market records")
                rows=db.execute("""SELECT symbol,interval,source,protocol,COUNT(*),MAX(created_at)
                    FROM reports WHERE market=? GROUP BY symbol,interval,source,protocol
                    ORDER BY symbol,interval,source,protocol""",(market,)).fetchall()
            result[market]={"status":"RESEARCH_ONLY" if rows else "AWAITING_EVIDENCE",
                "scopes":[dict(zip(("symbol","interval","source","protocol","reports","latest"),r)) for r in rows]}
        except (OSError,sqlite3.Error,ValueError):
            result[market]={"status":"DATA_REVIEW_REQUIRED","scopes":[]}
    return {"version":VERSION,"markets":result,"cross_market_training":False,
            "automatic_promotion":False,"real_orders":False}


def run(root, archive=None, import_paired=False):
    rows=[]
    if archive:
        raw=archive.read_bytes()
        rows.extend(equity_records(json.loads(raw),hashlib.sha256(raw).hexdigest()))
    if import_paired:
        with closing(readonly(root/"var/ai/paired-ai-review.sqlite3")) as db:
            for key,payload in db.execute("SELECT fingerprint,payload FROM paired_reports"):
                rows.append(paired_record(json.loads(payload),key))
    save(root,rows)
    return inventory(root)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--archive-report",type=Path)
    p.add_argument("--import-paired",action="store_true")
    p.add_argument("--initialize",action="store_true")
    args=p.parse_args()
    root=args.root.resolve()
    data=run(root,args.archive_report,args.import_paired) if (args.initialize or args.archive_report or args.import_paired) else inventory(root)
    print(json.dumps(data,indent=2,allow_nan=False))
