"""Durable opt-in paper-only intents and completed-day settlement replay.

Separate simulated cash per instrument. No broker or wallet integration.
"""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from tools.fund_etf_context import contextual_decision
from tools.fund_etf_refresh import validate
from tools.fund_etf_settlement import number, replay


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False)


def run_account(database, archive, account, report, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now > datetime.now(timezone.utc):
        raise ValueError("invalid_clock")
    pid = account["id"]
    identity = tuple(account[k] for k in ("market","symbol","currency","source"))
    market,symbol,currency,source = identity
    base = dict(id=pid,market=market,symbol=symbol,currency=currency,
                real_orders=False,execution_allowed=False,mode="paper_only")
    if account.get("enabled") is not True or account.get("terms_confirmed") is not True:
        return dict(base,status="disabled",reason_tr="Sanal hesap veya ürün koşulları onaylanmadı.")
    if not isinstance(pid,str) or not pid.strip() or len(pid)>100:
        raise ValueError("invalid_account_id")
    if Path(database).resolve()==Path(archive).resolve():
        raise ValueError("ledger_archive_collision")
    rules,sessions=account["rules"],account["sessions"]
    if not 2<=len(sessions)<=1500:
        raise ValueError("invalid_calendar_size")
    budget=number(account["initial_cash"],positive=True)
    fraction=number(account.get("max_entry_fraction","0.20"),positive=True)
    if fraction>Decimal(".25"):
        raise ValueError("paper_position_limit")
    zone=timezone.utc if rules["timezone"]=="UTC" else ZoneInfo(rules["timezone"])
    local=now.astimezone(zone)
    today=local.date()
    closed=today-timedelta(days=1)
    calendar={s["date"] for s in sessions}
    if not date.fromisoformat(sessions[0]["date"])<=closed or today>date.fromisoformat(rules["valid_to"]):
        return dict(base,status="blocked",reason_tr="Sanal hesap takvimi geçerli değil.")
    args=dict(market=market,symbol=symbol,currency=currency,rules=rules,sessions=sessions,
              initial_cash=str(budget),dividends=account.get("dividends",[]))
    terms=canonical(dict(args,source=source,max_entry_fraction=str(fraction)))
    with closing(sqlite3.connect(Path(archive).resolve().as_uri()+"?mode=ro",uri=True)) as db:
        rows=db.execute("SELECT market,symbol,session,currency,close,source FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? AND session<=? ORDER BY session",
                        identity+(closed.isoformat(),)).fetchall()
    validate(rows,*identity,max_age_days=7,min_rows=2,today=closed)
    prices={r[2]:str(number(r[4],positive=True)) for r in rows if r[2] in calendar}
    with closing(sqlite3.connect(database,timeout=20)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS fund_auto_accounts (id TEXT PRIMARY KEY,terms TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS fund_auto_orders (account TEXT,signal_session TEXT,order_id TEXT,timestamp TEXT,side TEXT,amount TEXT,reason_tr TEXT,PRIMARY KEY(account,signal_session),UNIQUE(account,order_id))")
        db.execute("CREATE TABLE IF NOT EXISTS fund_auto_prices (account TEXT,session TEXT,price TEXT,PRIMARY KEY(account,session))")
        db.execute("CREATE TABLE IF NOT EXISTS fund_auto_journal (account TEXT,digest TEXT,recorded_at TEXT,payload TEXT,PRIMARY KEY(account,digest))")
        existing=db.execute("SELECT terms FROM fund_auto_accounts WHERE id=?",(pid,)).fetchone()
        if existing and existing[0]!=terms:
            return dict(base,status="blocked",reason_tr="Hesap koşulları değişti; geçmiş kayıtlar korunuyor.")
        db.execute("INSERT INTO fund_auto_accounts VALUES (?,?) ON CONFLICT DO NOTHING",(pid,terms))
        previous=dict(db.execute("SELECT session,price FROM fund_auto_prices WHERE account=?",(pid,)))
        if any(d not in prices or Decimal(prices[d])!=Decimal(p) for d,p in previous.items()):
            return dict(base,status="blocked",reason_tr="Arşiv fiyat revizyonu veya eksik kayıt; işlem engellendi.")
        db.executemany("INSERT INTO fund_auto_prices VALUES (?,?,?) ON CONFLICT DO NOTHING",
                       [(pid,d,p) for d,p in prices.items()])
        history=[dict(id=r[0],timestamp=r[1],side=r[2],amount=r[3],reason_tr=r[4],signal_session=r[5])
                 for r in db.execute("SELECT order_id,timestamp,side,amount,reason_tr,signal_session FROM fund_auto_orders WHERE account=? ORDER BY timestamp,order_id",(pid,))]
        if any(datetime.fromisoformat(o["timestamp"])>now for o in history):
            return dict(base,status="blocked",reason_tr="Saat önceki emir kaydından geriye gitti.")
        past=[o for o in history if datetime.fromisoformat(o["timestamp"]).astimezone(zone).date()<=closed]
        current=[o for o in history if o not in past]
        state=replay(**args,prices=prices,orders=past,as_of=closed.isoformat())
        why="Yeni uygun araştırma sinyali yok."
        if state["pending"] or current or state["status"]!="paper_replay":
            why="Bekleyen emir veya valör tamamlanmadan yeni emir oluşturulmaz."
        elif len(history)>=1500:
            why="Sanal hesap kayıt sınırına ulaştı."
        else:
            matches=[i for i in report.get("instruments",[]) if
                     tuple((i.get("metrics") or {}).get(k) for k in ("market","symbol","currency","source"))==identity
                     and i.get("status")=="research_review" and i.get("research_eligible") is True]
            if len(matches)==1:
                item=matches[0]; m=item["metrics"]; signal=m["last_session"]
                cutoff=datetime.fromisoformat(report["analysis_cutoff"])
                fresh=0<=(now-cutoff).total_seconds()<=7200
                if (fresh and signal==rows[-1][2] and date.fromisoformat(signal)<today
                    and signal in calendar and all(o["signal_session"]!=signal for o in history)):
                    held=number(state["available_units"])>0
                    decision=contextual_decision(m,item["rank"],item["context"],held=held)
                    side=None
                    if held and decision["action"]=="SELL_REVIEW":
                        side="SELL"; amount=number(state["available_units"])
                    elif (not held and decision["action"]=="BUY_REVIEW"
                          and report.get("status")=="research_only"
                          and (item.get("decision") or {}).get("action")=="BUY_REVIEW"):
                        side="BUY"; amount=min(number(state["available_cash"]),budget*fraction)
                    if side and amount>0:
                        # Only schedule a price strictly after today, not a known close.
                        days=[date.fromisoformat(s["date"]) for s in sessions]
                        effective=next((i for i,d in enumerate(days) if d>today or
                            (d==today and local.time()<time.fromisoformat(sessions[i]["cutoff"]))),None)
                        if effective is not None:
                            prefix=side.lower()+"_"
                            pricing=effective+rules[prefix+"price_lag"]
                            settlement=effective+rules[prefix+"settlement_lag"]
                            if settlement<len(days) and pricing<len(days) and days[pricing]>today:
                                oid=hashlib.sha256(canonical([pid,signal,side]).encode()).hexdigest()[:32]
                                order=dict(id=oid,timestamp=now.isoformat(),side=side,amount=str(amount),
                                           reason_tr=decision["reason_tr"],signal_session=signal)
                                db.execute("INSERT INTO fund_auto_orders VALUES (?,?,?,?,?,?,?)",
                                           (pid,signal,oid,order["timestamp"],side,str(amount),order["reason_tr"]))
                                history.append(order); current.append(order)
                                why=decision["reason_tr"]
                        if not current:
                            why="İleri tarihli fiyat ve valör takvimi uygun değil."
        # Today's submissions are reserved immediately in the view but processed
        # only after the local day closes; never infer today's price.
        state["pending"] += [dict(id=o["id"],state="submitted_today",settlement_session=None) for o in current]
        for o in current:
            a=number(o["amount"])
            field="cash" if o["side"]=="BUY" else "units"
            state["available_"+field]=str(number(state["available_"+field])-a)
            state["reserved_"+field]=str(number(state["reserved_"+field])+a)
        if current:
            state["pnl"]=None
        out=dict(state,**base,history=history,reason_tr=why)
        payload=canonical(out)
        digest=hashlib.sha256(payload.encode()).hexdigest()
        db.execute("INSERT INTO fund_auto_journal VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                   (pid,digest,now.isoformat(),payload))
        return out


def run(database, archive, accounts, report, *, now=None):
    if not isinstance(accounts,list) or len(accounts)>10:
        raise ValueError("invalid_accounts")
    ids=[a["id"] for a in accounts]
    if len(set(ids))!=len(ids):
        raise ValueError("duplicate_account")
    results=[]
    for account in accounts:
        try:
            results.append(run_account(database,archive,account,report,now=now))
        except Exception as exc:
            results.append(dict(id=account.get("id"),market=account.get("market"),
                symbol=account.get("symbol"),currency=account.get("currency"),status="blocked",
                reason_tr="Sanal işlem için veri veya yapılandırma uygun değil.",
                error_type=type(exc).__name__,real_orders=False,execution_allowed=False))
    return results
