"""One explicit DexTerm screener research run; no pool/exit provider or execution."""
import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from cyberbot.db_paths import checked
from tools.dexterm_readonly_probe import probe
from tools.dexterm_candidate_review import review
from tools.dexterm_research_archive import archive, APP_ID, FLAGS


def run(root, database, *, enabled=False, probe_fn=probe):
    base = {**dict.fromkeys(FLAGS, False), "research_only": True,
            "pool_execution_verified": False, "exact_exit_available": False}
    if enabled is not True:
        return {**base, "status": "disabled"}
    if os.getenv("CYBERBOT_PILOT_KILL_SWITCH") != "1" or os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED") != "1":
        raise ValueError("Explicit research permissions and entry brake required")
    target = Path(database).resolve()
    # Require the same explicitly configured archive used by the central panel.
    configured = os.getenv("CYBERBOT_DEXTERM_ARCHIVE")
    if not configured or Path(configured).resolve() != target:
        raise ValueError("Configure the dedicated DexTerm archive path first")
    checked()
    if target.exists():
        from contextlib import closing
        with closing(sqlite3.connect(target.as_uri()+"?mode=ro", uri=True, timeout=1)) as db:
            if db.execute("PRAGMA application_id").fetchone()[0] != APP_ID or db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("Not a DexTerm archive")
    raw = probe_fn(root, True)
    if raw.get("source") != "dexterm_screener_query" or any(raw.get(k) is not False for k in FLAGS):
        raise ValueError("Unexpected screener authority")
    with tempfile.TemporaryDirectory(prefix="cyberbot-dexterm-research-") as folder:
        scan = Path(folder)/"scan.json"
        scan.write_text(json.dumps(raw, allow_nan=False), encoding="utf-8")
        reports = [scan]
        shortlist = None
        if raw["status"] == "diagnostic_complete":
            reviewed = review(raw)
            p = Path(folder)/"review.json"
            p.write_text(json.dumps(reviewed, allow_nan=False), encoding="utf-8")
            reports.append(p)
            shortlist = reviewed["shortlist_count"]
        saved = archive(target, reports)
    return {**base, "status": "screener_review_complete" if shortlist is not None else "screener_partial",
            "candidate_count": raw["candidate_count"], "shortlist_count": shortlist,
            "new_reports": saved["new_reports"], "total_reports": saved["total_reports"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dexterm-root", required=True)
    p.add_argument("--database", required=True)
    p.add_argument("--enable", action="store_true")
    a = p.parse_args()
    try:
        out = run(a.dexterm_root,a.database,enabled=a.enable)
        print(json.dumps(out,allow_nan=False))
        return 0 if out["status"] in ("disabled","screener_review_complete") else 2
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError, sqlite3.Error) as exc:
        print(json.dumps({"status":"rejected","error_type":type(exc).__name__,"real_orders":False}))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
