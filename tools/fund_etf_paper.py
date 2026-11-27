"""Offline paper ledger; no live execution, settlement or broker integration."""
import sqlite3
import math
from datetime import date

def connect(database):
    db=sqlite3.connect(database)
    db.execute("CREATE TABLE IF NOT EXISTS fund_paper_accounts (id TEXT PRIMARY KEY, market TEXT, currency TEXT, cash REAL, initial_cash REAL)")
    db.execute("CREATE TABLE IF NOT EXISTS fund_paper_positions (account TEXT,symbol TEXT,source TEXT,units REAL,PRIMARY KEY(account,symbol,source))")
    db.execute("CREATE TABLE IF NOT EXISTS fund_paper_trades (account TEXT,trade_id TEXT,symbol TEXT,source TEXT,side TEXT,session TEXT,price REAL,units REAL,fee REAL,PRIMARY KEY(account,trade_id))")
    return db

def create_account(database, account, market, currency, cash):
    if not account or market not in ("TEFAS","ETF") or currency not in ("TRY","USD","EUR","GBP") or (market=="TEFAS" and currency!="TRY") or not math.isfinite(cash) or cash<=0:
        raise ValueError("Invalid account")
    with connect(database) as db:
        db.execute("INSERT INTO fund_paper_accounts VALUES (?,?,?,?,?)",(account,market,currency,cash,cash))

def trade(database, account, trade_id, symbol, source, side, signal_date, session, units, *, cost_bps, max_position_fraction=0.2):
    if side not in ("BUY","SELL") or not trade_id or not symbol or not source or not math.isfinite(units) or units<=0 or not math.isfinite(cost_bps) or not 0<=cost_bps<10000 or not 0<max_position_fraction<=1:
        raise ValueError("Invalid order")
    if not date.fromisoformat(signal_date)<date.fromisoformat(session)<=date.today():
        raise ValueError("Execution must follow signal")
    with connect(database) as db:
        db.execute("BEGIN IMMEDIATE")
        a=db.execute("SELECT market,currency,cash,initial_cash FROM fund_paper_accounts WHERE id=?",(account,)).fetchone()
        if not a:
            raise ValueError("Unknown account")
        market,currency,cash,initial=a
        last=db.execute("SELECT MAX(session) FROM fund_paper_trades WHERE account=?",(account,)).fetchone()[0]
        if last and session<last:
            raise ValueError("Nonchronological trade")
        row=db.execute("SELECT close FROM fund_prices WHERE market=? AND symbol=? AND currency=? AND source=? AND session=?",(market,symbol,currency,source,session)).fetchone()
        if not row:
            raise ValueError("Missing observed price")
        price=float(row[0])
        if not math.isfinite(price) or price<=0:
            raise ValueError("Invalid price")
        pos=db.execute("SELECT units FROM fund_paper_positions WHERE account=? AND symbol=? AND source=?",(account,symbol,source)).fetchone()
        held=pos[0] if pos else 0
        gross=units*price
        fee=gross*cost_bps/10000
        if not math.isfinite(gross+fee):
            raise ValueError("Invalid notional")
        if side=="BUY":
            if gross+fee>cash or (held+units)*price>initial*max_position_fraction:
                raise ValueError("Cash or position limit exceeded")
            cash-=gross+fee
            held+=units
        else:
            if units>held:
                raise ValueError("Insufficient units")
            cash+=gross-fee
            held-=units
        db.execute("INSERT INTO fund_paper_trades VALUES (?,?,?,?,?,?,?,?,?)",(account,trade_id,symbol,source,side,session,price,units,fee))
        db.execute("INSERT INTO fund_paper_positions VALUES (?,?,?,?) ON CONFLICT(account,symbol,source) DO UPDATE SET units=excluded.units",(account,symbol,source,held))
        db.execute("UPDATE fund_paper_accounts SET cash=? WHERE id=?",(cash,account))
    return {"status":"historical_paper_fill","cash":cash,"units_held":held,"fee":fee,"real_orders":False,"settlement_verified":False}
