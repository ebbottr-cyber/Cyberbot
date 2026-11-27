"""Private local candidate store. Integrity is not authenticity.

Only locally trained, trusted model text may be loaded by native libraries.
Never import a model from the network. No production activation or orders.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from contextlib import closing

from .adaptive_review import readonly
from cyberbot.db_paths import checked, pilot_path, same

VERSION = "local-model-registry-1"
MAX_MODEL_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 20
SCOPE = ("FUTURES","BTCUSDT","1m","binance-usdm-public")
FEATURES = ("mean","ar1","chronos")


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate(meta, text):
    if (meta["version"] != VERSION or meta["model"] != "lightgbm"
            or tuple(meta["scope"]) != SCOPE or tuple(meta["features"]) != FEATURES
            or meta["evidence_status"] != "EXPLORATORY_UNVERIFIED"
            or meta["automatic_promotion"] is not False
            or meta["live_prediction_verified"] is not False
            or meta["real_orders"] is not False):
        raise ValueError("invalid candidate metadata")
    if not isinstance(meta["library_version"],str) or not re.fullmatch(r"[0-9][A-Za-z0-9.+-]{0,63}",meta["library_version"]):
        raise ValueError("invalid library version")
    if not re.fullmatch(r"[a-f0-9]{64}",meta["source_fingerprint"]):
        raise ValueError("invalid data fingerprint")
    if (type(meta["train_samples"]) is not int or meta["train_samples"]<60
            or type(meta["test_samples"]) is not int or meta["test_samples"]<20
            or type(meta["last_train_target"]) is not int
            or type(meta["first_test_target"]) is not int
            or meta["last_train_target"]+22>meta["first_test_target"]):
        raise ValueError("invalid training boundary")
    for n in ("naive_mae_pct","model_mae_pct"):
        x=meta[n]
        if type(x) not in (int,float) or not math.isfinite(x) or x<0:
            raise ValueError("invalid metric")
    if not isinstance(text,str) or not text.startswith("tree\n"):
        raise ValueError("expected native LightGBM model text")
    raw=text.encode("utf-8")
    if len(raw)>MAX_MODEL_BYTES or sha(raw)!=meta["model_sha256"]:
        raise ValueError("model size or integrity mismatch")
    return sha(canonical(meta).encode())


def path_for(root):
    path=Path(root).resolve()/"var/ai/candidate-models.sqlite3"
    protected=[*checked().values(),pilot_path(),
               *checked(Path(root)/"var/paper.sqlite3").values(),
               pilot_path(Path(root)/"var/paper.sqlite3")]
    protected.extend(Path(root)/"var/ai"/n for n in (
        "forward-models-v2.sqlite3","lightgbm-review-journal.sqlite3",
        "river-replay-journal.sqlite3","paired-ai-review.sqlite3"))
    if path.is_symlink() or (path.exists() and path.stat().st_nlink!=1):
        raise ValueError("unsafe candidate path")
    if any(same(path.resolve(),p.resolve()) for p in protected):
        raise ValueError("protected database collision")
    return path


def save(root, meta, text):
    if os.environ.get("CYBERBOT_LOCAL_RESEARCH_RIGHTS_CONFIRMED")!="1":
        raise RuntimeError("research rights confirmation required")
    candidate=validate(meta,text)
    path=path_for(root)
    path.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(path,timeout=10)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS model_candidates (
                candidate TEXT PRIMARY KEY, metadata TEXT NOT NULL, model_text TEXT NOT NULL
            )""")
            row=db.execute("SELECT metadata,model_text FROM model_candidates WHERE candidate=?",
                           (candidate,)).fetchone()
            if row is not None:
                if validate(json.loads(row[0]),row[1])!=candidate or row!=(canonical(meta),text):
                    raise ValueError("existing candidate mismatch")
            else:
                if db.execute("SELECT COUNT(*) FROM model_candidates").fetchone()[0]>=MAX_CANDIDATES:
                    raise RuntimeError("candidate limit reached; manual review required")
                db.execute("INSERT INTO model_candidates VALUES (?,?,?)",
                           (candidate,canonical(meta),text))
            if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                raise RuntimeError("candidate database integrity failed")
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return candidate


def read(root, candidate, library_version):
    if not isinstance(candidate,str) or not re.fullmatch(r"[a-f0-9]{64}",candidate):
        raise ValueError("invalid candidate id")
    with closing(readonly(path_for(root))) as db:
        row=db.execute("SELECT metadata,model_text FROM model_candidates WHERE candidate=?",
                       (candidate,)).fetchone()
    if row is None:
        raise ValueError("candidate not found")
    meta,text=json.loads(row[0]),row[1]
    if validate(meta,text)!=candidate or meta["library_version"]!=library_version:
        raise ValueError("candidate identity or library version mismatch")
    return meta,text
