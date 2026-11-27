"""Run under an external single-instance supervisor; no automatic startup."""
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone

def run_periodic(cycle, health_path, stop_event, *, enabled=False, interval=300):
    if not enabled:
        return "disabled"
    if not 60 <= interval <= 3600:
        raise ValueError("Invalid interval")
    path = Path(health_path)
    while not stop_event.is_set():
        started = datetime.now(timezone.utc).isoformat()
        tick = time.monotonic()
        try:
            result = cycle()
            sources = result.get("sources", {})
            state = "degraded" if any(s.get("status") == "error" for s in [*sources.values(), result.get("research_news", {}), result.get("existing_news_bridge", {})]) else result.get("status", "unknown")
            health = {"status": state, "started_at": started}
        except Exception as exc:
            health = {"status": "error", "started_at": started, "error_type": type(exc).__name__}
        health["finished_at"] = datetime.now(timezone.utc).isoformat()
        health["duration_seconds"] = round(time.monotonic() - tick, 3)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(health), encoding="utf-8")
        os.replace(temp, path)
        stop_event.wait(interval)
    return "stopped"
