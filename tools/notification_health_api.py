"""Read-only notification health; never exposes subscription endpoints."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends

def snapshot(health_path, queue, push_store, *, stale_seconds=900):
    health = {"status": "unknown", "age_seconds": None}
    try:
        data = json.loads(Path(health_path).read_text(encoding="utf-8"))
        finished = datetime.fromisoformat(data["finished_at"])
        if finished.tzinfo is None:
            raise ValueError("Timezone required")
        age = (datetime.now(timezone.utc)-finished).total_seconds()
        health = {"status": "stale" if age > stale_seconds or age < 0 else data.get("status","unknown"),
                  "age_seconds": round(age), "finished_at": finished.isoformat()}
    except (OSError, ValueError, TypeError, KeyError):
        pass
    with closing(sqlite3.connect(queue.path)) as db:
        counts = dict(db.execute("SELECT state, COUNT(*) FROM push_queue GROUP BY state"))
    return {"worker": health, "queue": {key: counts.get(key,0) for key in ("pending","accepted","failed","expired")},
            "subscriptions": len(push_store.subscriptions()),
            "device_delivery_verified": False}

def build_health_router(health_path, queue, push_store, require_user):
    if not callable(require_user):
        raise ValueError("Authentication required")
    router = APIRouter(prefix="/api/notifications", dependencies=[Depends(require_user)])
    @router.get("/health")
    def health():
        return snapshot(health_path, queue, push_store)
    return router
