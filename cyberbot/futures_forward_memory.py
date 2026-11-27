"""Local forward prediction journal. No risk permission or order submission.

One prediction per nonoverlapping five-minute target, persisted before the
target is collected. Missing outcomes remain missing. Local clock/database
integrity is assumed, not externally attested.
"""
import argparse,json,os,sqlite3
from contextlib import closing
from datetime import timedelta
from . import db_paths, futures_lightgbm as batch, futures_training as training
from . import futures_ai_bridge as bridge, observed_pilot as stocks

VERSION="futures-forward-memory-1"
TABLE="forward_predictions_v1"
WINDOW=1200
MAX_ISSUE_AGE=30
GRACE=120
KEEP=2016
FLAGS=("CYBERBOT_FUTURES_FORWARD_MEMORY_ENABLED","CYBERBOT_FUTURES_LIGHTGBM_ENABLED","CYBERBOT_FUTURES_RIVER_ENABLED")
def permitted():return training.enabled() and all(os.getenv(k)=="1" for k in FLAGS)
def path():
    db_paths.checked();return db_paths.futures_forward_path()
def schema(db,create=False):
    names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
    if names and names!={TABLE}:raise batch.ResearchError("İleri tahmin hafıza şeması uyuşmuyor.")
    if not names and create:
        db.execute("CREATE TABLE "+TABLE+"(symbol TEXT NOT NULL,feature_at TEXT NOT NULL,target_at TEXT NOT NULL,issued_at TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(symbol,feature_at))")
    return bool(names) or create
def result(symbol,status,**fields):
    return {"version":VERSION,"symbol":symbol,"status":status,"actual_action":"HOLD","paper_orders":False,"real_orders":False,
            "promotion_enabled":False,"independent_provenance_verified":False,"profitability_verified":False,**fields}
def exact_window(symbol,start,end,now):
    p=training.path()
    if not p.is_file():return []
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        if not training.schema(db):return []
        values=db.execute("SELECT at,payload FROM "+training.TABLE+" WHERE symbol=? AND at BETWEEN ? AND ? ORDER BY at",
                          (symbol,start.isoformat(),end.isoformat())).fetchall()
    out=[]
    for key,payload in values:
        rec=json.loads(payload);sym,at=training.validate_record(rec,now)
        if sym!=symbol or at.isoformat()!=key:raise batch.ResearchError("Gözlem kimliği uyuşmuyor.")
        out.append(rec)
    return out
def settle(db,symbol,now):
    changed={"scored":0,"missing":0}
    pending=db.execute("SELECT feature_at,target_at,issued_at,payload FROM "+TABLE+" WHERE symbol=? AND status='pending' AND target_at<=? ORDER BY feature_at",
                       (symbol,now.isoformat())).fetchall()
    for feature,target,issued,payload in pending:
        start=batch.timestamp(feature);end=batch.timestamp(target);when=stocks.ts(issued)
        if end-start!=batch.HORIZON*batch.STEP or not start<=when<=start+timedelta(seconds=MAX_ISSUE_AGE):
            raise batch.ResearchError("Tahmin zamanları geçersiz.")
        d=json.loads(payload)
        rows=exact_window(symbol,start,end,now)
        complete=(len(rows)==batch.HORIZON+1 and all(batch.timestamp(r["row"]["at"])==start+i*batch.STEP for i,r in enumerate(rows)))
        if not complete:
            if now<end+timedelta(seconds=GRACE):continue
            status="missing";d["missing_reason"]="incomplete_exact_window"
        else:
            # Target acquisition must begin after the prediction was issued.
            if stocks.ts(rows[-1]["started_at"])<=when or batch.numeric(rows[0]["row"]["mid"],1e-8,1e9)!=d["feature_mid"]:
                raise batch.ResearchError("Tahmin ve sonuç kaynakları uyuşmuyor.")
            actual=batch.numeric(float(rows[-1]["row"]["mid"])/d["feature_mid"]-1,-1,1)
            d.update(actual_return=actual,actual_direction=batch.direction(actual),
                     target_received_at=rows[-1]["received_at"],resolved_at=now.isoformat())
            status="scored"
        db.execute("UPDATE "+TABLE+" SET status=?,payload=? WHERE symbol=? AND feature_at=? AND status='pending'",
                   (status,json.dumps(d,allow_nan=False),symbol,feature))
        changed[status]+=1
    return changed
def latest(db,symbol):
    return db.execute("SELECT feature_at,target_at,issued_at FROM "+TABLE+" WHERE symbol=? ORDER BY feature_at DESC LIMIT 1",(symbol,)).fetchone()
def transaction(symbol,*,clock,callback):
    p=path();p.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(p,timeout=5,isolation_level=None)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            schema(db,True);out=callback(db,clock());db.commit();return out
        except BaseException:db.rollback();raise
def tick(symbol,*,clock=stocks.utc):
    if not permitted():raise batch.ResearchError("İleri tahmin hafıza izni kapalı.")
    training.symbol_check(symbol)
    def prepare(db,now):
        resolved=settle(db,symbol,now)
        return resolved,latest(db,symbol)
    resolved,prior=transaction(symbol,clock=clock,callback=prepare)
    now=clock()
    if prior and now<stocks.ts(prior[2]):raise batch.ResearchError("Yerel saat geriledi.")
    if prior and now<batch.timestamp(prior[1]):return result(symbol,"waiting_for_target",resolved=resolved)
    raw=training.recent(symbol,clock=lambda:now)
    if len(raw)<WINDOW:return result(symbol,"waiting_for_data",resolved=resolved)
    rows=batch.validate(raw[-WINDOW:],symbol,now);at=rows[-1]["at"]
    if not 0<=(now-at).total_seconds()<=MAX_ISSUE_AGE:return result(symbol,"stale_features",resolved=resolved)
    if prior and at<batch.timestamp(prior[1]):return result(symbol,"overlapping_target",resolved=resolved)
    p=bridge.forecast(rows)
    if p.get("estimator_injected") is not False or batch.timestamp(p["feature_at"])!=at or p["feature_mid"]!=rows[-1]["mid"]:
        raise batch.ResearchError("Tahmin kaynağı geçersiz.")
    predictions={k:batch.numeric(p[k+"_return"],-1,1) for k in ("lightgbm","river")}
    predictions.update(zero=0.0,trailing_momentum=batch.numeric(batch.features(rows,len(rows)-1)[1],-1,1))
    target=at+batch.HORIZON*batch.STEP
    def insert(db,issued):
        if not 0<=(issued-at).total_seconds()<=MAX_ISSUE_AGE:return result(symbol,"forecast_expired",resolved=resolved)
        previous=latest(db,symbol)
        if previous and (at<batch.timestamp(previous[1]) or issued<stocks.ts(previous[2])):
            return result(symbol,"duplicate_or_overlapping",resolved=resolved)
        d={"feature_mid":rows[-1]["mid"],"predictions":predictions,"model_versions":{"lightgbm":batch.VERSION,"river":bridge.online.VERSION,"forecast":bridge.VERSION},
           "directions":{k:batch.direction(v) for k,v in predictions.items()}}
        db.execute("INSERT INTO "+TABLE+" VALUES(?,?,?,?,?,?)",(symbol,at.isoformat(),target.isoformat(),issued.isoformat(),"pending",json.dumps(d,allow_nan=False)))
        db.execute("DELETE FROM "+TABLE+" WHERE symbol=? AND status!='pending' AND feature_at NOT IN (SELECT feature_at FROM "+TABLE+" WHERE symbol=? ORDER BY feature_at DESC LIMIT ?)",(symbol,symbol,KEEP))
        return result(symbol,"recorded",feature_at=at.isoformat(),target_at=target.isoformat(),issued_at=issued.isoformat(),resolved=resolved)
    return transaction(symbol,clock=clock,callback=insert)
def snapshot(symbol):
    training.symbol_check(symbol)
    p=path();rows=[]
    if p.is_file():
        with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
            db.execute("PRAGMA query_only=ON")
            if schema(db):rows=db.execute("SELECT status,payload FROM "+TABLE+" WHERE symbol=? ORDER BY feature_at DESC LIMIT ?",(symbol,KEEP)).fetchall()
    counts={s:sum(k==s for k,_ in rows) for s in ("pending","scored","missing")}
    scored=[json.loads(v) for k,v in rows if k=="scored"]
    metrics={}
    if scored:
        actual=[d["actual_return"] for d in scored]
        for k in ("lightgbm","river","zero","trailing_momentum"):
            metrics[k]=batch.metrics([d["predictions"][k] for d in scored],actual)
    return result(symbol,"read_only",retained_predictions=len(rows),counts=counts,metrics=metrics,
                  outcome_coverage_pct=100*counts["scored"]/(counts["scored"]+counts["missing"]) if counts["scored"]+counts["missing"] else None,
                  all_directions_included=True,nonoverlapping_targets=True,model_promotion_evidence=False)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"));p.add_argument("--tick",action="store_true")
    a=p.parse_args()
    try:
        print(json.dumps(tick(a.symbol) if a.tick else snapshot(a.symbol),ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as exc:
        print(json.dumps({"status":"rejected","type":type(exc).__name__,"actual_action":"HOLD","real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
