"""Persist distinct historical evaluation inputs, not claims of learning success."""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

VERSION = "fund-etf-evidence-v1"
MARKETS = ("TEFAS", "ETF")
STAGES = ("backtest", "model_review")


def encode(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"))


def record(database, archive, item, recorded_at):
    """Record completed evaluations once per input, stage and fixed policy version."""
    m = item["metrics"]
    identity = tuple(m[k] for k in ("market","symbol","currency","source"))
    if identity[0] not in MARKETS or Path(database).resolve()==Path(archive).resolve():
        raise ValueError("invalid_evidence_scope")
    with closing(sqlite3.connect(Path(archive).resolve().as_uri()+"?mode=ro",uri=True)) as db:
        rows=db.execute("SELECT session,close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? ORDER BY session",identity).fetchall()
    if not rows or rows[-1][0]!=m["last_session"]:
        raise ValueError("evidence_snapshot_mismatch")
    price_hash=hashlib.sha256(encode(rows).encode()).hexdigest()
    added=0
    with closing(sqlite3.connect(database,timeout=20)) as db,db:
        db.execute("""CREATE TABLE IF NOT EXISTS fund_development (
            id TEXT PRIMARY KEY, market TEXT NOT NULL,symbol TEXT NOT NULL,currency TEXT NOT NULL,
            source TEXT NOT NULL,stage TEXT NOT NULL,last_session TEXT NOT NULL,
            recorded_at TEXT NOT NULL,payload TEXT NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS fund_development_scope ON fund_development(market,symbol,currency,source,stage,last_session)")
        for stage in STAGES:
            report=item.get(stage)
            if not isinstance(report,dict) or report.get("real_orders") is not False:
                continue
            if stage=="backtest":
                policy={k:report.get(k) for k in ("cost_bps","lag_observations","train_observations","test_observations","risk_penalty")}
                payload={k:report.get(k) for k in ("status","fold_count","summary")}
            else:
                # cycle uses model_review defaults; bump VERSION if those change.
                policy={"min_train":100,"horizon":5,"step":20,"min_samples":100}
                payload={k:report.get(k) for k in ("status","candidate","models","ranking","reason_tr")}
            key=hashlib.sha256(encode([VERSION,identity,stage,price_hash,policy]).encode()).hexdigest()
            payload.update(policy=policy,price_hash=price_hash,observations=len(rows),
                           model_promoted=False,independent_evidence=False,real_orders=False)
            cursor=db.execute("INSERT OR IGNORE INTO fund_development VALUES (?,?,?,?,?,?,?,?,?)",
                (key,*identity,stage,m["last_session"],recorded_at,encode(payload)))
            added+=cursor.rowcount
    return added


def overview(database):
    result=dict(status="empty",markets=[dict(market=m,records=0,latest=[]) for m in MARKETS],
                recent=[],real_orders=False,model_promoted=False,profitability_verified=False,
                independent_evidence_verified=False)
    path=Path(database).resolve()
    if not path.is_file():
        return result
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fund_development'").fetchone():
            return result
        def unpack(row):
            key,market,symbol,currency,source,stage,session,recorded,payload=row
            return dict(id=key,market=market,symbol=symbol,currency=currency,source=source,
                        stage=stage,last_session=session,recorded_at=recorded,report=json.loads(payload))
        for m in result["markets"]:
            market=m["market"]
            m["records"]=db.execute("SELECT COUNT(*) FROM fund_development WHERE market=?",(market,)).fetchone()[0]
            rows=db.execute("""SELECT id,market,symbol,currency,source,stage,last_session,recorded_at,payload FROM (
                SELECT *,ROW_NUMBER() OVER (PARTITION BY symbol,currency,source,stage
                ORDER BY last_session DESC,recorded_at DESC,id DESC) AS rn FROM fund_development WHERE market=?
                ) WHERE rn=1 ORDER BY last_session DESC,recorded_at DESC,id DESC LIMIT 30""",(market,)).fetchall()
            m["latest"]=[unpack(r) for r in rows]
        result["recent"]=[unpack(r) for r in db.execute("SELECT id,market,symbol,currency,source,stage,last_session,recorded_at,payload FROM fund_development ORDER BY recorded_at DESC,id DESC LIMIT 30")]
    result["status"]="recorded" if any(m["records"] for m in result["markets"]) else "empty"
    return result
