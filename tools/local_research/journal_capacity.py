"""Non-destructive admission limits for the four local learning journals.

Count SQLite sidecars as well as the main file. These are soft admission
thresholds, not filesystem quotas. No deletion, truncation or checkpoint.
"""
import argparse
import json
from pathlib import Path
import stat

MIB = 1024**2
LIMITS = {
    "forward-models-v2.sqlite3": 512*MIB,
    "river-live-shadow.sqlite3": 256*MIB,
    "river-replay-journal.sqlite3": 128*MIB,
    "lightgbm-review-journal.sqlite3": 128*MIB,
}
MODES = {
    "Chronos": "forward-models-v2.sqlite3",
    "RiverLive": "river-live-shadow.sqlite3",
    "RiverReplay": "river-replay-journal.sqlite3",
    "LightGBM": "lightgbm-review-journal.sqlite3",
}
TOTAL_LIMIT = 1024*MIB
SUFFIXES = ("", "-wal", "-shm", "-journal")


def safe_stat(path):
    try:
        s = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(s.st_mode) or getattr(s,"st_file_attributes",0)&1024:
        raise ValueError("unsafe research path")
    return s


def inventory(root):
    root=Path(root)
    folder=root/"var/ai"
    for p in (folder.parent,folder):
        s=safe_stat(p)
        if s is None:
            return {"status":"NOT_AVAILABLE","journals":{},"automatic_deletion":False}
        if not stat.S_ISDIR(s.st_mode):
            raise ValueError("unsafe research folder")
    journals={}
    for name,limit in LIMITS.items():
        total=0
        for suffix in SUFFIXES:
            s=safe_stat(folder/(name+suffix))
            if s is not None:
                if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:
                    raise ValueError("unsafe research journal")
                total+=s.st_size
        journals[name]={"bytes":total,"admission_limit_bytes":limit,
                        "status":"LIMIT_REACHED" if total>=limit else "BELOW_LIMIT"}
    used=sum(item["bytes"] for item in journals.values())
    return {"status":"LIMIT_REACHED" if used>=TOTAL_LIMIT or any(
                j["status"]=="LIMIT_REACHED" for j in journals.values()) else "BELOW_LIMIT",
            "journals":journals,"total_bytes":used,"total_admission_limit_bytes":TOTAL_LIMIT,
            "automatic_deletion":False,"hard_quota":False}


def require_capacity(root, mode):
    if mode not in MODES:
        raise ValueError("unsupported research mode")
    report=inventory(root)
    if report["status"]=="NOT_AVAILABLE":
        raise ValueError("research directory missing")
    if (report["total_bytes"]>=TOTAL_LIMIT or
            report["journals"][MODES[mode]]["status"]=="LIMIT_REACHED"):
        print("WAIT_JOURNAL_CAPACITY:",mode,flush=True)
        raise SystemExit(75)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--mode",choices=tuple(MODES))
    args=p.parse_args()
    report=require_capacity(args.root,args.mode) if args.mode else inventory(args.root)
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=="__main__":
    main()
