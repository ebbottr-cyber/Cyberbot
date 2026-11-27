"""Train, verify and persist a local LightGBM research candidate."""
import argparse
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import shutil

from .adaptive_review import readonly
from .lightgbm_journal import prepare, train_lightgbm, MIN_TRAIN, MIN_TEST, MAX_ROWS
from .model_registry import VERSION, SCOPE, FEATURES, canonical, sha, save, read
from .vps_guard import MIB, MIN_FREE_DISK_MIB


def build(rows, *, train_model, reload_model, library_version, array=list):
    train,test=prepare(rows)
    if len(train)<MIN_TRAIN or len(test)<MIN_TEST:
        return None,None
    model=train_model([r[2] for r in train],[r[3] for r in train])
    x=array([r[2] for r in test])
    predicted=list(model.predict(x,num_threads=2))
    text=model.model_to_string()
    restored=reload_model(text)
    again=list(restored.predict(x,num_threads=2))
    if len(predicted)!=len(test) or len(again)!=len(test):
        raise ValueError("prediction count mismatch")
    if any(not math.isfinite(float(a)) or float(a)<=-100
           or not math.isfinite(float(b))
           or not math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-10)
           for a,b in zip(predicted,again)):
        raise ValueError("model round-trip verification failed")
    from statistics import mean
    meta={"version":VERSION,"model":"lightgbm","scope":list(SCOPE),
          "features":list(FEATURES),"library_version":library_version,
          "source_fingerprint":hashlib.sha256(canonical(rows).encode()).hexdigest(),
          "model_sha256":sha(text.encode()),"train_samples":len(train),
          "test_samples":len(test),"last_train_target":train[-1][0],
          "first_test_target":test[0][0],
          "naive_mae_pct":mean(r[4]["naive"] for r in test),
          "model_mae_pct":mean(abs(r[3]-float(p)) for r,p in zip(test,predicted)),
          "evidence_status":"EXPLORATORY_UNVERIFIED","automatic_promotion":False,
          "live_prediction_verified":False,"real_orders":False}
    return meta,text


def run(root):
    if os.environ.get("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("research rights confirmation required")
    folder=root/"var/ai"
    if shutil.disk_usage(folder).free//MIB<MIN_FREE_DISK_MIB:
        raise RuntimeError("insufficient disk")
    with closing(readonly(folder/"forward-models-v2.sqlite3")) as db:
        rows=db.execute("""SELECT target_minute,created_at,payload,outcome FROM (
            SELECT target_minute,created_at,payload,outcome FROM forecasts
            WHERE market=? AND symbol=? AND source=? AND status='measured'
            ORDER BY target_minute DESC LIMIT ?) ORDER BY target_minute""",
            (SCOPE[0],SCOPE[1],SCOPE[3],MAX_ROWS)).fetchall()
    import lightgbm as lgb
    import numpy as np
    meta,text=build(rows,train_model=train_lightgbm,
                    reload_model=lambda s:lgb.Booster(model_str=s),
                    library_version=lgb.__version__,array=np.asarray)
    base={"automatic_promotion":False,"real_orders":False,"live_prediction_verified":False}
    if meta is None:
        return {**base,"status":"INSUFFICIENT_EVIDENCE"}
    candidate=save(root,meta,text)
    read(root,candidate,lgb.__version__)
    return {**base,"status":"CANDIDATE_SAVED","candidate":candidate,
            "metadata":meta,"round_trip_verified":True}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    print(json.dumps(run(p.parse_args().root.resolve()),indent=2,allow_nan=False))
