"""Isolated persistent Futures AI research history; never stores model weights or orders."""
import argparse,hashlib,json,os,sqlite3
from contextlib import closing
from datetime import timedelta
from . import db_paths,futures_ai_consensus as ai,futures_lightgbm as batch
from .observed_pilot import utc

VERSION="futures-ai-memory-1"
KEEP=200
MODELS=("lightgbm","river")
METRICS=(*MODELS,"zero","trailing_momentum")
TABLES={"ai_runs","ai_states"}

def enabled():return os.getenv("CYBERBOT_FUTURES_AI_MEMORY_ENABLED")=="1"
def path():
    db_paths.checked()
    return db_paths.futures_ai_memory_path()
def integer(v,lo,hi):
    if type(v) is not int or not lo<=v<=hi:raise batch.ResearchError("Hafıza örnek sayısı geçersiz.")
    return v
def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)

def compact(d,now):
    if (not isinstance(d,dict) or d.get("version")!=ai.VERSION or d.get("status")!="offline_common_window_research"
        or d.get("data_mode")!="local_observations_unverified" or d.get("symbol") not in ("BTCUSDT","ETHUSDT")
        or d.get("horizon_minutes")!=5 or d.get("same_test_window") is not True
        or d.get("actual_action")!="HOLD" or any(d.get(k) is not False for k in
        ("real_orders","paper_orders","promotion_enabled","profitability_verified","feature_provenance_verified"))):
        raise batch.ResearchError("AI araştırma raporu kimliği geçersiz.")
    if d.get("estimator_injected") is not False or d.get("runtime_verified") is not True:
        raise batch.ResearchError("Deneme adaptörü sonuçları kalıcı performans kanıtı değildir.")
    start=batch.timestamp(d["test_first_feature_at"]);end=batch.timestamp(d["test_last_target_at"])
    trained=batch.timestamp(d["training_last_target_at"])
    if not trained<start<end<=now:raise batch.ResearchError("AI kanıtı zaman aralığı geçersiz.")
    all_n=integer(d["all_test"]["examples"],50,batch.MAX_ROWS)
    if end-start!=(all_n-1+batch.HORIZON)*batch.STEP:raise batch.ResearchError("AI test zaman aralığı uyuşmuyor.")
    window=d["nonoverlapping_test"];n=integer(window["examples"],ai.MIN_NONOVERLAP,batch.MAX_ROWS)
    if n!=(all_n+batch.HORIZON-1)//batch.HORIZON:raise batch.ResearchError("AI çakışmayan örnek sayısı tutarsız.")
    metrics={}
    for name in METRICS:
        v=window["metrics"][name]
        metrics[name]={"mae_pct":batch.numeric(v["mae_pct"],0,200),
                       "direction_accuracy_pct":batch.numeric(v["direction_accuracy_pct"],0,100)}
    alarms=d["drift_events"]
    if not isinstance(alarms,list) or len(alarms)>n:raise batch.ResearchError("Drift kayıt sayısı geçersiz.")
    previous=None
    for alarm in alarms:
        a=batch.timestamp(alarm["prediction_at"]);b=batch.timestamp(alarm["detected_at"])
        if not start<=a<b<=end or b-a!=5*batch.STEP or (a-start)%(5*batch.STEP)!=timedelta(0) or (previous and a<=previous):
            raise batch.ResearchError("Drift olay zamanı geçersiz.")
        previous=a
    return {"symbol":d["symbol"],"start":start.isoformat(),"end":end.isoformat(),
            "examples":n,"metrics":metrics,"drift_count":len(alarms)}

def initial():
    return {"runs":0,"examples":0,"mae_pct":None,"direction_accuracy_pct":None,
            "weak_streak":0,"recovery_streak":0,"status":"observing","reason":"no_evidence",
            "last_end":None}
def update(state,evidence,name):
    s=dict(state);n=evidence["examples"];total=s["examples"]+n
    metric=evidence["metrics"][name]
    for field in ("mae_pct","direction_accuracy_pct"):
        s[field]=((s[field] or 0)*s["examples"]+metric[field]*n)/total
    s.update(runs=s["runs"]+1,examples=total,last_end=evidence["end"])
    good=metric["mae_pct"]<min(evidence["metrics"][k]["mae_pct"] for k in ("zero","trailing_momentum"))
    drift=name=="river" and evidence["drift_count"]>0
    if drift:s.update(status="quarantined",reason="drift_alarm",weak_streak=0,recovery_streak=0)
    elif s["status"]=="quarantined":
        s["recovery_streak"]=s["recovery_streak"]+1 if good else 0
        if s["recovery_streak"]>=3:s.update(status="observing",reason="three_recovery_windows",weak_streak=0,recovery_streak=0)
    else:
        s["weak_streak"]=0 if good else s["weak_streak"]+1
        if s["weak_streak"]>=2:s.update(status="quarantined",reason="two_weak_windows",recovery_streak=0)
    return s

def schema(db,create=False):
    actual={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
    if actual and actual!=TABLES:raise batch.ResearchError("AI hafıza veritabanı şeması uyuşmuyor.")
    if not actual and create:
        db.execute("CREATE TABLE ai_runs(id TEXT PRIMARY KEY,symbol TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL,payload TEXT NOT NULL)")
        db.execute("CREATE TABLE ai_states(symbol TEXT PRIMARY KEY,payload TEXT NOT NULL)")
    return bool(actual) or create

def states(db,symbol):
    row=db.execute("SELECT payload FROM ai_states WHERE symbol=?",(symbol,)).fetchone()
    return json.loads(row[0]) if row else {k:initial() for k in MODELS}

def record(report,*,clock=utc):
    if not enabled():raise batch.ResearchError("AI hafıza izni kapalı.")
    e=compact(report,clock());sym=e["symbol"]
    key=hashlib.sha256(canonical([VERSION,ai.VERSION,sym,e["start"],e["end"]]).encode()).hexdigest()
    p=path();p.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(p,timeout=5,isolation_level=None)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            schema(db,create=True);s=states(db,sym)
            if any(v["last_end"] is not None and e["start"]<v["last_end"] for v in s.values()) or any(v["last_end"]==e["end"] for v in s.values()):
                db.rollback()
                return {"status":"overlapping_or_old","id":key,"symbol":sym,"states":s,"recorded":False,"promotion_enabled":False,"real_orders":False}
            s={k:update(s[k],e,k) for k in MODELS}
            db.execute("INSERT INTO ai_runs VALUES(?,?,?,?,?)",(key,sym,e["start"],e["end"],canonical(e)))
            db.execute("INSERT INTO ai_states VALUES(?,?) ON CONFLICT(symbol) DO UPDATE SET payload=excluded.payload",(sym,canonical(s)))
            db.execute("DELETE FROM ai_runs WHERE symbol=? AND id NOT IN (SELECT id FROM ai_runs WHERE symbol=? ORDER BY end DESC LIMIT ?)",(sym,sym,KEEP))
            db.commit()
        except BaseException:
            db.rollback();raise
    return {"status":"recorded","id":key,"symbol":sym,"states":s,"recorded":True,
            "promotion_enabled":False,"real_orders":False}

def snapshot(symbol):
    if symbol not in ("BTCUSDT","ETHUSDT"):raise batch.ResearchError("Sembol geçersiz.")
    out={"version":VERSION,"status":"empty","symbol":symbol,"states":{k:initial() for k in MODELS},
         "recent":[],"data_mode":"local_observations_unverified","promotion_enabled":False,"real_orders":False}
    p=path()
    if not p.is_file():return out
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
        if not schema(db):return out
        out["states"]=states(db,symbol)
        out["recent"]=[json.loads(row[0]) for row in db.execute("SELECT payload FROM ai_runs WHERE symbol=? ORDER BY end DESC LIMIT 20",(symbol,))]
        if out["recent"]:out["status"]="recorded"
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"))
    p.add_argument("--input",help="Local observation JSON; absent means read-only status")
    a=p.parse_args()
    try:
        if a.input:
            if not enabled():raise batch.ResearchError("AI hafıza izni kapalı.")
            report=ai.run(batch.read_local(a.input),symbol=a.symbol,as_of=utc())
            result=record(report)
        else:result=snapshot(a.symbol)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as exc:
        print(json.dumps({"status":"rejected","type":type(exc).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
