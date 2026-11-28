"""Single offline-first research cycle for TEFAS and ETF; never submits orders."""
import argparse
import json
import math
import os
import sqlite3
import tempfile
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from tools.fund_etf_refresh import run as refresh, validate
from tools.tefas_catalog import scan as scan_tefas
from tools.etf_catalog import scan as scan_etf
from tools.fund_etf_scoring import rank_group
from tools.fund_etf_context import context, contextual_decision
from tools.fund_etf_gemini import explain
from tools.fund_etf_panel import snapshot
from tools.fund_etf_walkforward import from_archive
from tools.fund_etf_ai_review import model_review

MARKETS = ("TEFAS", "ETF")


def cycle(database, config, *, yahoo_enabled=False):
    """Run once. Optional network refresh requires explicit provider opt-in.

    A frozen SQLite copy ensures consistent analysis. Expensive historical model
    evaluations are separately opt-in and bounded; they never promote a model.
    """
    start = datetime.now(timezone.utc)
    result = dict(schema_version=1, generated_at=start.isoformat(),
                  status="blocked", mode="research_only", markets=[],
                  groups=[], instruments=[], errors=[], real_orders=False,
                  execution_allowed=False, live_data_verified=False)
    age = config.get("max_age_days",7)
    limit = config.get("max_instruments",1000)
    expensive = config.get("evaluation_limit",0)
    peers = config.get("min_peers",5)
    if (type(age) is not int or age<0 or type(limit) is not int or not 1<=limit<=5000
            or type(expensive) is not int or not 0<=expensive<=10
            or type(peers) is not int or peers<5):
        raise ValueError("invalid_cycle_policy")
    sources = config.get("sources",{"TEFAS":"TEFAS","ETF":"Yahoo Finance"})
    if set(sources)!=set(MARKETS) or any(not isinstance(v,str) or not v.strip() for v in sources.values()):
        raise ValueError("invalid_sources")
    jobs=config.get("refresh_jobs",[])
    if jobs:
        result["refresh"]=refresh(database,jobs,yahoo_enabled=yahoo_enabled)
        if result["refresh"]["status"]!="quality_checked":
            result["errors"].append("refresh_failed")
            return result
    path=Path(database).resolve()
    if not path.is_file():
        result["errors"].append("archive_missing")
        return result
    cutoff=datetime.now(timezone.utc)
    result["analysis_cutoff"]=cutoff.isoformat()
    with tempfile.TemporaryDirectory() as folder:
        frozen=Path(folder)/"snapshot.sqlite3"
        with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as src, closing(sqlite3.connect(frozen)) as dst:
            src.backup(dst)
        with closing(sqlite3.connect(frozen)) as db, db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts={market:db.execute("SELECT COUNT(*) FROM "+table).fetchone()[0] if table in tables else 0
                    for market,table in (("TEFAS","tefas_catalog"),("ETF","etf_catalog"))}
            if sum(counts.values())>limit:
                result["errors"].append("catalog_limit_exceeded")
                return result
            # Daily records lack publication timestamps. Exclude the current UTC
            # day conservatively; this is not a verified publication calendar.
            if "fund_prices" in tables:
                db.execute("DELETE FROM fund_prices WHERE session>=?",(cutoff.date().isoformat(),))
        result["markets"]=snapshot(frozen)["markets"]
        groups=defaultdict(list)
        for market in MARKETS:
            if not counts[market]:
                result["errors"].append(market+"_catalog_missing_or_empty")
                continue
            try:
                entries=(scan_tefas(frozen,source=sources[market],max_age_days=age)
                         if market=="TEFAS" else
                         scan_etf(frozen,price_source=sources[market],max_age_days=age))
            except Exception as exc:
                result["errors"].append(market+"_scan_"+type(exc).__name__)
                continue
            for entry in entries:
                m=entry.get("metrics",{})
                item=dict(entry,market=market,rank=None,decision=None,context=None)
                result["instruments"].append(item)
                if not entry["research_eligible"]:
                    item["status"]="data_unavailable"
                    continue
                try:
                    with closing(sqlite3.connect(frozen)) as db, db:
                        rows=db.execute("SELECT market,symbol,session,currency,close,source FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=?",
                                        (market,m["symbol"],m["currency"],m["source"])).fetchall()
                    validate(rows,market,m["symbol"],m["currency"],m["source"],max_age_days=age,min_rows=21)
                    key=(market,entry.get("category") or entry.get("sector"),
                         m["currency"],m["source"],m["last_session"])
                    if not key[1] or not all(math.isfinite(m[k]) for k in
                        ("last_20_observation_return_pct","max_drawdown_pct","observation_volatility_pct")):
                        raise ValueError("invalid_peer_metrics")
                    groups[key].append(item)
                    item["status"]="quality_checked"
                except Exception:
                    item.update(status="quality_blocked",research_eligible=False)
        candidates=[]
        for key,items in sorted(groups.items()):
            market,group,currency,source,session=key
            # Do not compare duplicate symbol identities within a peer group.
            if len({e["symbol"].upper() for e in items})!=len(items):
                ranked={"status":"ambiguous_peer_identity","scores":[]}
            else:
                ranked=rank_group(items,min_peers=peers)
            result["groups"].append(dict(market=market,group=group,currency=currency,
                                         source=source,last_session=session,
                                         status=ranked["status"],peer_count=len(items)))
            scores={r["symbol"]:r for r in ranked["scores"]}
            for item in items:
                score=scores.get(item["symbol"])
                if score is None:
                    item["status"]="unranked"
                    continue
                item["rank"]=score
                m=item["metrics"]
                try:
                    info=context(frozen,market,m["symbol"],cutoff.isoformat(),
                                 config.get("macro_series",{}).get(market,[]))
                    item["context"]=info
                    decision=contextual_decision(m,score,info)
                    item["decision"]=decision
                    item["explanation"]=explain(decision,m)  # Local only in bulk scans.
                    item["status"]="research_review"
                    candidates.append(item)
                except Exception as exc:
                    item.update(status="context_blocked",error_type=type(exc).__name__)
        # Scores are relative to groups. Do not rank unlike categories globally.
        # Allocate limited historical evaluations round-robin across peer groups.
        by_group=defaultdict(list)
        for item in candidates:
            m=item["metrics"]
            key=(item["market"],item.get("category") or item.get("sector"),m["currency"],m["source"],m["last_session"])
            by_group[key].append(item)
        for values in by_group.values():
            values.sort(key=lambda e:(-e["rank"]["research_score"],e["symbol"]))
            for i,item in enumerate(values,1):
                item["peer_rank"]=i
        ordered=[item for i in range(max(map(len,by_group.values()),default=0))
                 for key in sorted(by_group) if i<len(by_group[key]) for item in [by_group[key][i]]]
        for item in ordered[:expensive]:
            m=item["metrics"]
            args=(frozen,item["market"],m["symbol"],m["currency"],m["source"])
            try:
                report=from_archive(*args)
                item["backtest"]={k:v for k,v in report.items() if k!="folds"}
                if config.get("evaluate_models") is True:
                    item["model_review"]=model_review(*args)
            except Exception as exc:
                item["evaluation_error"]=type(exc).__name__
        result["status"]=("partial" if result["errors"] or any(
            i["status"]!="research_review" or i.get("evaluation_error") for i in result["instruments"])
            else "research_only") if candidates else "blocked"
    result["counts"]={"instruments":len(result["instruments"]),"ranked":len(candidates),
                      "buy_review":sum(i["decision"]["action"]=="BUY_REVIEW" for i in candidates)}
    return result


def publish(report, output):
    """Atomic snapshot replacement; old snapshot survives write failure."""
    path=Path(output).resolve()
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(report,f,ensure_ascii=False,allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database",required=True)
    p.add_argument("--config",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--enable-yahoo",action="store_true")
    a=p.parse_args()
    if Path(a.output).resolve() in (Path(a.database).resolve(),Path(a.config).resolve()):
        p.error("output must not replace input")
    with open(a.config,encoding="utf-8") as f:
        config=json.load(f)
    report=cycle(a.database,config,yahoo_enabled=a.enable_yahoo)
    publish(report,a.output)
    return 0 if report["status"]=="research_only" else 2


if __name__=="__main__":
    raise SystemExit(main())
