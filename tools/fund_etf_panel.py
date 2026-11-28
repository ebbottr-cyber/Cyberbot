"""Read-only panel snapshot. No router registration or execution."""
import sqlite3
from contextlib import closing
from pathlib import Path

def snapshot(database):
    result={"markets":[],"real_orders":False,"live_data_verified":False,"mode":"research_only"}
    path=Path(database).resolve()
    if not path.is_file():
        result["status"]="archive_missing"
        return result
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as db, db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for market in ("TEFAS","ETF"):
            item={"market":market,"title":"TEFAS Fonları" if market=="TEFAS" else "Global ETF","price_observations":0,"last_session":None,"accounts":[],"news_count":0,"live_data_verified":False}
            if "fund_prices" in tables:
                item["price_observations"],item["last_session"]=db.execute("SELECT COUNT(*),MAX(session) FROM fund_prices WHERE market=?",(market,)).fetchone()
            if "fund_paper_accounts" in tables:
                item["accounts"]=[{"id":r[0],"currency":r[1],"cash":r[2],"initial_cash":r[3],"marked_equity":None} for r in db.execute("SELECT id,currency,cash,initial_cash FROM fund_paper_accounts WHERE market=? ORDER BY id",(market,))]
            if "fund_news" in tables:
                item["news_count"]=db.execute("SELECT COUNT(*) FROM fund_news WHERE market=?",(market,)).fetchone()[0]
            item["status"]="archived_data" if item["price_observations"] else "no_data"
            result["markets"].append(item)
    result["status"]="research_only"
    return result
