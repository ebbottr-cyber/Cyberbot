"""Explicit bounded observation cycles. No automatic entry, broker or task installation."""
import os,json,sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from . import observed_pilot as stocks,pilot_decisions as decisions
from .providers import equity_observed as equity,binance_observed as binance
from .pilot_ingress import ingest
from .worker import worker_path
from .operations import inspect_db,required
from .observed_pilot import PilotError,ts

VERSION="pilot-loop-1"
MARKETS=("BIST","NASDAQ","XETRA","SOLANA","FUTURES")
MIN_INTERVAL=15
MAX_FAILURE_DELAY=300
def enabled():
    return os.getenv("CYBERBOT_PILOT_LOOP_ENABLED")=="1" and decisions.enabled() and os.getenv("CYBERBOT_PILOT_INGRESS_ENABLED")=="1"
def selected():
    raw=os.getenv("CYBERBOT_PILOT_LOOP_MARKETS","")
    items=raw.split(",")
    if not items or any(x not in MARKETS for x in items) or len(set(items))!=len(items):raise PilotError("Açık piyasa listesi gerekli.")
    return items
def local_input(m,name):
    p=os.getenv("CYBERBOT_LOOP_"+name+"_"+m)
    if not p:raise PilotError("Yerel fiyat/seans dosyası ayarı eksik.")
    path=Path(p).expanduser().resolve()
    if not path.is_file():raise PilotError("Yerel dosya mevcut değil.")
    return equity.read_json(path)
def local_quote(m,*,clock):
    now=clock()
    env=equity.prepare(m,local_input(m,"QUOTE"),local_input(m,"SCHEDULE"),now)
    q=stocks.validate(m,env["quote"],now);p=stocks.path()
    if p.is_file():
        with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=2)) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='observed_accounts'").fetchone():
                s=stocks.load(db,m);old=s["quote"]
                if old and ts(old["source_at"])==ts(q["source_at"]):
                    a={k:v for k,v in old.items() if k!="received_at"};b={k:v for k,v in q.items() if k!="received_at"}
                    if a!=b:raise PilotError("Aynı zamanlı farklı kotasyon.")
                    return {"status":"awaiting_new_quote","applied":False}
    result=ingest(env,clock=clock)
    return {"status":result["status"],"applied":True}
def observe_market(m,*,clock):
    if m in equity.VENUES:return local_quote(m,clock=clock)
    if m=="FUTURES":
        # Public polling requires the existing provider and pilot permissions.
        d=binance.run(apply=True,clock=clock)
        return {"status":d["ingress"]["status"],"applied":bool(d["applied"])}
    # Jupiter diagnostic data are not a validated USD quote/depth/security envelope.
    return {"status":"provider_blocked","applied":False}
def snapshot(*,clock=stocks.utc):
    result={"version":VERSION,"enabled":enabled(),"status":"not_started","last_cycle":None,"recent":[],"heartbeat_fresh":False,"running_verified":False,"automatic_entry_enabled":False,"real_orders":False}
    p=worker_path()
    if not p.is_file():return result
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=1)) as db:
        db.execute("PRAGMA query_only=ON")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pilot_cycles'").fetchone():return result
        recent=[json.loads(r[0]) for r in db.execute("SELECT payload FROM pilot_cycles ORDER BY id DESC LIMIT 20")]
    if recent:
        last=recent[0];age=(clock()-ts(last["finished_at"])).total_seconds()
        result.update(status="recorded" if 0<=age<=60 else "historical",last_cycle=last,recent=recent,heartbeat_fresh=0<=age<=60)
    return result
def run_cycle(*,clock=stocks.utc):
    if not enabled():raise PilotError("Çalışma döngüsü/gölge karar/veri izinleri kapalı.")
    markets=selected();p=worker_path();pilot=stocks.path()
    if pilot.is_file() and inspect_db(pilot,required("observed_pilot"))!="ok":raise PilotError("Gözlem kasası bütünlüğü doğrulanamadı.")
    p.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(p,timeout=1,isolation_level=None)) as db:
        try:db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():return {"status":"busy","real_orders":False}
            raise
        try:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{"cycles","settings","pilot_cycles","pilot_loop_state"}:raise PilotError("Zamanlayıcı DB şeması uyumsuz.")
            db.execute("CREATE TABLE IF NOT EXISTS pilot_cycles(id INTEGER PRIMARY KEY,payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS pilot_loop_state(market TEXT PRIMARY KEY,payload TEXT NOT NULL)")
            now=clock();latest=db.execute("SELECT payload FROM pilot_cycles ORDER BY id DESC LIMIT 1").fetchone()
            if latest:
                elapsed=(now-ts(json.loads(latest[0])["finished_at"])).total_seconds()
                if elapsed<MIN_INTERVAL:
                    db.rollback();return {"status":"throttled" if elapsed>=0 else "clock_regressed","real_orders":False}
            report={"version":VERSION,"status":"ok","started_at":now.isoformat(),"markets":[],"automatic_entry_enabled":False,"real_orders":False,"bulk_price_download_enabled":False}
            for m in markets:
                current=clock();row=db.execute("SELECT payload FROM pilot_loop_state WHERE market=?",(m,)).fetchone()
                prior=json.loads(row[0]) if row else {"failures":0,"retry_at":None}
                item={"market":m,"status":"disabled","applied":False,"decision":None}
                if not decisions.market_enabled(m):report["status"]="degraded"
                elif prior["retry_at"] and current<ts(prior["retry_at"]):
                    item.update(status="backoff",retry_at=prior["retry_at"],failures=prior["failures"]);report["status"]="degraded"
                else:
                    try:
                        result=observe_market(m,clock=clock);item.update(result)
                        if item["applied"]:
                            d=decisions.record(m,clock=clock)
                            item["decision"]={"status":d["status"],"recorded":d.get("recorded",False),"actual_action":"HOLD"}
                        if item["status"] in ("provider_blocked","awaiting_new_quote"):report["status"]="degraded"
                        next_state={"failures":0,"retry_at":None}
                    except Exception as exc:
                        failures=min(prior["failures"]+1,10);delay=min(MAX_FAILURE_DELAY,60*2**(failures-1))
                        next_state={"failures":failures,"retry_at":(clock()+timedelta(seconds=delay)).isoformat()}
                        item.update(status="failed",error_type=type(exc).__name__,**next_state);report["status"]="degraded"
                    db.execute("INSERT INTO pilot_loop_state VALUES(?,?) ON CONFLICT(market) DO UPDATE SET payload=excluded.payload",(m,json.dumps(next_state)))
                report["markets"].append(item)
            report["finished_at"]=clock().isoformat()
            db.execute("INSERT INTO pilot_cycles(payload) VALUES(?)",(json.dumps(report,ensure_ascii=False,allow_nan=False),))
            db.execute("DELETE FROM pilot_cycles WHERE id NOT IN (SELECT id FROM pilot_cycles ORDER BY id DESC LIMIT 1000)")
            db.commit();return report
        except BaseException:
            db.rollback();raise
