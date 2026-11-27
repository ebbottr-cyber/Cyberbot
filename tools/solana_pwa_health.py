"""Bounded read-only host and backup status for the authenticated Solana panel."""
import math
from datetime import datetime,timezone
from pathlib import Path
from tools.solana_pc_health import health
from tools.solana_research_backup import load_manifest,FILES,MAX_SETS,MAX_DB_BYTES
from tools.solana_paper_replay import instant,FALSE_FLAGS

MAX_DIRECTORY_ENTRIES=500
BACKUP_OVERDUE_SECONDS=26*3600
STATES={"ready","running","partial","stopped","error","unavailable","invalid"}
BLOCKERS={"low_disk_space","ram_measurement_unavailable","low_available_ram",
          "operator_review_stop_marker","scheduler_lock_present"}
WARNINGS={"cpu_measurement_unavailable","high_cpu_sample","publication_stale",
          "last_research_incomplete","invalid_publication"}

def integer(value):
    if type(value) is not int or not 0<=value<=2**63-1:raise ValueError("Invalid resource count")
    return value

def optional_int(value):
    return None if value is None else integer(value)

def percentage(value):
    if value is None:return None
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100:
        raise ValueError("Invalid CPU sample")
    return value

def empty_backup(state):
    return {"state":state,"last_created_utc":None,"age_seconds":None,"sets":None,
            "capacity":MAX_SETS,"bytes":None,"records":None,"integrity_rechecked":False}

def backup_status(root,now):
    folder=root/"backups"
    if folder.is_symlink():raise ValueError("Invalid backup folder")
    if not folder.exists():return empty_backup("unavailable")
    if not folder.is_dir():raise ValueError("Invalid backup folder")
    sets=[]
    for i,path in enumerate(folder.iterdir(),1):
        if i>MAX_DIRECTORY_ENTRIES:raise ValueError("Backup directory scan limit")
        if path.name.startswith("solana-") and not path.is_symlink() and path.is_dir():sets.append(path)
        if len(sets)>MAX_SETS:raise ValueError("Backup set limit")
    out=empty_backup("unavailable");out["sets"]=len(sets)
    if not sets:return out
    # The backup writer uses sortable UTC names; do not silently fall back
    # from an incomplete/corrupt newest set to an older healthy-looking one.
    latest=max(sets,key=lambda x:x.name)
    m=load_manifest(latest);stamp=instant(m["created_utc"])
    if stamp>now:raise ValueError("Future backup")
    size=records=0
    for name in FILES:
        item=m["files"][name]
        n=integer(item["bytes"])
        if n>MAX_DB_BYTES:raise ValueError("Invalid backup size")
        file=latest/name
        if file.is_symlink() or not file.is_file() or file.stat().st_size!=n:
            raise ValueError("Backup file size mismatch")
        size+=n;records+=integer(item["records"])
    age=int((now-stamp).total_seconds())
    out.update(state="overdue" if age>BACKUP_OVERDUE_SECONDS else "manifest_present",
               last_created_utc=stamp.isoformat(),age_seconds=age,bytes=size,records=records)
    return out

def unavailable(state="unavailable"):
    return {"schema_version":1,"market":"solana","health_state":state,
            "sampled_utc":None,"resource_scope":"host_not_bot_process",
            "cpu_sample_pct":None,"total_ram_bytes":None,"available_ram_bytes":None,
            "disk_free_bytes":None,"disk_total_bytes":None,"stop_marker_present":None,
            "lock_marker_present":None,"publication_state":"unavailable","publication_stale":None,
            "process_liveness_verified":False,"task_state_verified":False,
            "blockers":[],"warnings":[],"backup":empty_backup("unavailable"),
            "research_only":True,**FALSE_FLAGS}

def status(data_root):
    if not data_root:return unavailable()
    root=Path(data_root).resolve(strict=True)
    raw=health(root);now=datetime.now(timezone.utc)
    if raw["research_only"] is not True or any(raw.get(k) is not False for k in FALSE_FLAGS):
        raise ValueError("Unexpected health authority")
    if raw["status"] not in ("preflight_ok","preflight_blocked") or raw["publication_state"] not in STATES:
        raise ValueError("Unexpected health state")
    out=unavailable(raw["status"])
    out.update(sampled_utc=now.isoformat(),cpu_sample_pct=percentage(raw["cpu_sample_pct"]),
               publication_state=raw["publication_state"])
    for key in ("total_ram_bytes","available_ram_bytes","disk_free_bytes","disk_total_bytes"):
        out[key]=optional_int(raw[key])
    for key in ("stop_marker_present","lock_marker_present"):
        if type(raw[key]) is not bool:raise ValueError("Invalid marker state")
        out[key]=raw[key]
    stale=raw["publication_stale"]
    if stale is not None and type(stale) is not bool:raise ValueError("Invalid publication age state")
    out["publication_stale"]=stale
    for key,allowed in (("blockers",BLOCKERS),("warnings",WARNINGS)):
        values=raw[key]
        if not isinstance(values,list) or any(v not in allowed for v in values):raise ValueError("Invalid health reason")
        out[key]=list(values)
    try:out["backup"]=backup_status(root,now)
    except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError,OSError):
        out["backup"]=empty_backup("invalid")
    return out
