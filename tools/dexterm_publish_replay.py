"""Explicit offline DexTerm position replay publication for the central dashboard."""
import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from cyberbot.db_paths import checked, same
from cyberbot.dexterm_replay_status import summarize, MAX_BYTES
from tools.dexterm_paper_positions import replay


def publish(*, enabled=False, replay_fn=replay):
    base={"research_only":True,"real_orders":False,"live_data_verified":False}
    if enabled is not True:
        return {**base,"status":"disabled"}
    if os.getenv("CYBERBOT_PILOT_KILL_SWITCH")!="1" or os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise ValueError("Explicit research permissions and entry brake required")
    archive=os.getenv("CYBERBOT_DEXTERM_ARCHIVE")
    report=os.getenv("CYBERBOT_DEXTERM_REPLAY_REPORT")
    if not archive or not report:
        raise ValueError("Configure dedicated archive and replay paths")
    source=Path(archive).resolve(strict=True)
    target=Path(report).resolve()
    checked()
    if same(source,target) or target.suffix.lower()!=".json" or not target.parent.is_dir():
        raise ValueError("Separate replay JSON path required")
    if target.exists():
        with target.open("rb") as stream:
            previous=stream.read(MAX_BYTES+1)
        if len(previous)>MAX_BYTES:
            raise ValueError("Existing report too large")
        summarize(json.loads(previous.decode("utf-8-sig")))
    result=replay_fn(source,risk_mode=True,limit=100)
    clean=summarize(result)
    if result.get("bridge_history_truncated") is not False or result.get("exit_history_truncated") is not False:
        raise ValueError("Truncated research history; no publication")
    raw=json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf-8")
    if len(raw)>MAX_BYTES:
        raise ValueError("Replay report too large")
    fd,temp=tempfile.mkstemp(prefix=".dexterm-replay-",dir=target.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,target)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return {**base,"status":"replay_published","replay":clean}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--enable",action="store_true")
    a=p.parse_args()
    try:
        print(json.dumps(publish(enabled=a.enable),allow_nan=False))
        return 0
    except (OSError,ValueError,TypeError,KeyError,ArithmeticError,sqlite3.Error) as exc:
        print(json.dumps({"status":"rejected","error_type":type(exc).__name__,"real_orders":False}))
        return 1

if __name__=="__main__":raise SystemExit(main())
