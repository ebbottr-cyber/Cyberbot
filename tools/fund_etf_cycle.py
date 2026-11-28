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
from tools.fund_etf_risk import assess
from tools.fund_etf_portfolio import optimize
from tools.fund_etf_settlement import replay
from tools.fund_etf_macro import import_macro
from tools.fund_etf_news import ingest as ingest_news
from tools.fund_etf_auto_paper import run as run_auto_paper
from tools.fund_etf_development import record as record_development
from tools.fund_etf_source_check import compare_sources
from tools.fund_etf_context_collect import run as collect_context
from tools.fund_etf_safety import archive_paths, check_paths, exclusive

MARKETS = ("TEFAS", "ETF")


def cycle(database, config, *, yahoo_enabled=False):
    """Run once. Optional network refresh requires explicit provider opt-in.

    A frozen SQLite copy ensures consistent analysis. Expensive historical model
    evaluations are separately opt-in and bounded; they never promote a model.
    """
    archive_paths(database)  # Before any refresh or ledger writer.
    start = datetime.now(timezone.utc)
    result = dict(schema_version=1, generated_at=start.isoformat(),
                  status="blocked", mode="research_only", markets=[],
                  groups=[], instruments=[], portfolios=[], paper_replays=[], auto_paper=[], optimizations=[], errors=[], real_orders=False,
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
    paper_accounts=config.get("paper_accounts",[])
    if not isinstance(paper_accounts,list) or len(paper_accounts)>10:
        raise ValueError("invalid_paper_accounts")
    paper_ids=[a["id"] for a in paper_accounts]
    if any(not isinstance(i,str) or not i.strip() for i in paper_ids) or len(set(paper_ids))!=len(paper_ids):
        raise ValueError("invalid_paper_ids")
    portfolios=config.get("portfolios",[])
    if not isinstance(portfolios,list) or len(portfolios)>10:
        raise ValueError("invalid_portfolios")
    ids=[p["id"] for p in portfolios]
    if any(not isinstance(i,str) or not i.strip() for i in ids) or len(set(ids))!=len(ids):
        raise ValueError("invalid_portfolio_ids")
    jobs=config.get("refresh_jobs",[])
    if jobs:
        result["refresh"]=refresh(database,jobs,yahoo_enabled=yahoo_enabled)
        if result["refresh"]["status"]!="quality_checked":
            result["errors"].append("refresh_failed")
            return result
    # Optional user-authorized local files refreshed by an external data export.
    # Import all context before freezing the database. No hidden HTTP scraper.
    try:
        imports=config.get("context_imports",[])
        if not isinstance(imports,list) or len(imports)>20:
            raise ValueError("invalid_context_imports")
        for job in imports:
            if job.get("rights_confirmed") is not True:
                raise ValueError("context_source_not_authorized")
            source_path=Path(job["file"])
            if source_path.stat().st_size>10_000_000:
                raise ValueError("context_file_too_large")
            if job["kind"]=="macro_csv":
                import_macro(database,source_path,job["source"])
            elif job["kind"]=="news_json":
                with source_path.open(encoding="utf-8-sig") as f:
                    news=json.load(f)
                if not isinstance(news,list) or len(news)>5000:
                    raise ValueError("invalid_news_batch")
                ingest_news(database,news)
            else:
                raise ValueError("unsupported_context_import")
    except Exception as exc:
        result["errors"].append("context_import_"+type(exc).__name__)
        return result
    collection_jobs=config.get("context_collection",[])
    if collection_jobs:
        result["context_collection"]=collect_context(database,collection_jobs)
        if result["context_collection"]["status"]!="collected":
            result["errors"].append("context_collection_failed")
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
        checks=config.get("source_checks",[])
        if not isinstance(checks,list) or len(checks)>100:
            raise ValueError("invalid_source_checks")
        result["source_checks"]=[]
        for check in checks:
            try:
                result["source_checks"].append(compare_sources(frozen,**check))
            except Exception as exc:
                result["source_checks"].append(dict(status="blocked",error_type=type(exc).__name__,real_orders=False))
        if any(c["status"]!="research_agreement" for c in result["source_checks"]):
            result["errors"].append("source_agreement_review_required")
        for portfolio in portfolios:
            pid=portfolio["id"]
            args={k:v for k,v in portfolio.items() if k!="id"}
            args["as_of"]=cutoff.date().isoformat()
            args.setdefault("max_age_days",age)
            try:
                risk=assess(frozen,**args)
                result["portfolios"].append(dict(risk,id=pid))
                if risk["status"]!="research_only":
                    result["errors"].append("portfolio_review_required")
            except Exception as exc:
                result["portfolios"].append(dict(id=pid,status="blocked",
                    error_type=type(exc).__name__,real_orders=False))
                result["errors"].append("portfolio_assessment_failed")
        for section,fn,key in (("optimizations",optimize,"optimizations"),("paper_replays",None,"paper_replays")):
            requests=config.get(section,[])
            if not isinstance(requests,list) or len(requests)>10:
                raise ValueError("invalid_research_requests")
            for job in requests:
                job_id=job.get("id")
                try:
                    args={k:v for k,v in job.items() if k!="id"}
                    if fn:
                        report=fn(frozen,**args)
                    else:
                        if "prices" in args:
                            raise ValueError("paper_prices_must_come_from_archive")
                        source=args.pop("source")
                        with closing(sqlite3.connect(frozen)) as db:
                            rows=db.execute("SELECT session,close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? AND session<=? ORDER BY session",
                                (args["market"],args["symbol"],args["currency"],source,args["as_of"])).fetchall()
                        calendar={s["date"] for s in args["sessions"]}
                        args["prices"]={d:p for d,p in rows if d in calendar}
                        report=replay(**args)
                    result[key].append(dict(report,id=job_id))
                    if report["status"] not in ("research_only","paper_replay"):
                        result["errors"].append(section+"_review_required")
                except Exception as exc:
                    result[key].append(dict(id=job_id,status="blocked",error_type=type(exc).__name__,real_orders=False))
                    result["errors"].append(section+"_failed")
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
                    if decision["action"]=="BUY_REVIEW" and (any(
                        p["status"]!="research_only" for p in result["portfolios"]
                    ) or any(c["status"]!="research_agreement" for c in result["source_checks"])):
                        decision.update(action="WAIT",reason_tr="Portföy riski veya kaynak uyumu incelemesi tamamlanmadı.")
                    item["decision"]=decision
                    item["explanation"]=explain(decision,m)  # Optional Gemini on bounded subset below.
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
        gemini=config.get("gemini",{})
        gemini_limit=gemini.get("limit",0)
        if type(gemini_limit) is not int or not 0<=gemini_limit<=10:
            raise ValueError("invalid_gemini_limit")
        if gemini.get("enabled") is True and gemini.get("free_tier_confirmed") is True:
            for item in ordered[:gemini_limit]:
                item["explanation"]=explain(item["decision"],item["metrics"],enabled=True,
                    free_tier_confirmed=True,model=gemini.get("model"))
        for item in ordered[:expensive]:
            m=item["metrics"]
            args=(frozen,item["market"],m["symbol"],m["currency"],m["source"])
            try:
                report=from_archive(*args)
                item["backtest"]={k:v for k,v in report.items() if k!="folds"}
                if config.get("evaluate_models") is True:
                    item["model_review"]=model_review(*args)
                evidence=path.with_name(path.name+".development.sqlite3")
                item["new_evidence_records"]=record_development(evidence,frozen,item,cutoff.isoformat())
            except Exception as exc:
                item["evaluation_error"]=type(exc).__name__
        result["status"]=("partial" if result["errors"] or any(
            i["status"]!="research_review" or i.get("evaluation_error") for i in result["instruments"])
            else "research_only") if candidates else "blocked"
        if paper_accounts:
            ledger=path.with_name(path.name+".auto-paper.sqlite3")
            result["auto_paper"]=run_auto_paper(ledger,frozen,paper_accounts,result)
            if any(a["status"]=="blocked" for a in result["auto_paper"]):
                result["errors"].append("auto_paper_review_required")
                if result["status"]=="research_only":
                    result["status"]="partial"
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
    try:
        locks=check_paths(a.database,a.config,a.output)
    except (OSError,ValueError,sqlite3.Error) as exc:
        p.error("unsafe fund ETF paths: "+type(exc).__name__)
    with open(a.config,encoding="utf-8-sig") as f:
        config=json.load(f)
    for lock in locks:
        lock.parent.mkdir(parents=True,exist_ok=True)
    with exclusive(locks[0]), exclusive(locks[1]):
        report=cycle(a.database,config,yahoo_enabled=a.enable_yahoo)
        publish(report,a.output)
    return 0 if report["status"]=="research_only" else 2


if __name__=="__main__":
    raise SystemExit(main())
