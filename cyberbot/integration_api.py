"""Read-only integration status for the existing local, guarded web/PWA."""
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter
from .readiness import snapshot as readiness_snapshot

router = APIRouter()
APP_ID = 0x43594458
KINDS = ("screener", "review", "bridge", "exit_quote", "token2022", "token2022_review")
MARKETS = ("BIST", "NASDAQ", "XETRA", "FUTURES", "SOLANA")


def dexterm_status(path=None, *, now=None):
    result = {"source": "DexTerm", "status": "not_configured",
              "reports": None, "last_import_utc": None, "archive_freshness": "unknown",
              "live_data_verified": False, "paper_execution_verified": False,
              "research_only": True, "real_orders": False}
    path = path or os.getenv("CYBERBOT_DEXTERM_ARCHIVE")
    if not path:
        return result
    try:
        file = Path(path).resolve()
        if not file.is_file():
            result["status"] = "archive_missing"
            return result
        with closing(sqlite3.connect(file.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("PRAGMA application_id").fetchone()[0] != APP_ID or db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("Not a DexTerm archive")
            db.execute("BEGIN")
            rows = db.execute("SELECT kind, COUNT(*), MAX(imported_utc) FROM research_reports GROUP BY kind").fetchall()
            if any(kind not in KINDS for kind, _, _ in rows):
                raise ValueError("Unexpected report kind")
            count = sum(n for _, n, _ in rows)
            times = [datetime.fromisoformat(t) for _, _, t in rows]
            clock = now or datetime.now(timezone.utc)
            if any(t.tzinfo is None or t > clock for t in times):
                raise ValueError("Invalid archive time")
            latest = max(times) if times else None
        result.update(status="archive_available" if count else "archive_empty", reports=count,
                      last_import_utc=latest.astimezone(timezone.utc).isoformat() if latest else None,
                      archive_freshness=("recent_import" if (clock-latest).total_seconds() <= 3600 else "stale_import") if latest else "unknown")
    except (OSError, RuntimeError, sqlite3.Error, ValueError, TypeError, OverflowError):
        result["status"] = "archive_unavailable"
    return result


def integration_status():
    try:
        readiness = readiness_snapshot()
    except (OSError, RuntimeError, sqlite3.Error, ValueError, KeyError, TypeError, ArithmeticError):
        readiness = {"markets": [], "status": "unavailable"}
    existing = {row["market"]: row for row in readiness.get("markets", [])}
    dex = dexterm_status()
    markets = []
    for name in MARKETS:
        if name == "SOLANA":
            markets.append({"market": name, "source": "DexTerm", "data_status": dex["status"],
                            "live_data_verified": False, "paper_execution_verified": False,
                            "blockers": ["DexTerm arşivi yalnız araştırma kaydıdır; canlı veri ve sanal dolum doğrulanmadı."]})
        else:
            row = existing.get(name, {})
            markets.append({"market": name, "source": "Binance USD-M" if name == "FUTURES" else name,
                            "data_status": row.get("data", {}).get("status", "unavailable"),
                            "live_data_verified": row.get("live_data_verified") is True,
                            "paper_execution_verified": row.get("paper_execution_verified") is True,
                            "blockers": row.get("blockers", ["Hazırlık kaydı okunamadı."])})
    return {"version": "central-market-1", "markets": markets, "dexterm": dex,
            "readiness_status": readiness.get("status", "unavailable"),
            "real_orders": False, "automatic_entry_enabled": False}


@router.get("/api/integration/status")
def status():
    return integration_status()

AI_MODELS = ("chronos", "river", "lightgbm", "gemini")
AI_STATES = {"NOT_AVAILABLE", "NO_REPORT", "RESEARCH_MEASURED", "INSUFFICIENT_EVIDENCE",
             "DATA_REVIEW_REQUIRED", "RECORDED_NOT_REVALIDATED", "NO_LOCAL_ATTEMPTS",
             "OK", "RESERVED", "PROVIDER_ERROR"}


def ai_status():
    """Consume the optional research inventory, not model execution."""
    result = {"status": "not_integrated", "models": {}, "scheduler": "unknown",
              "real_orders": False, "automatic_promotion": False,
              "paper_readiness_verified": False}
    try:
        from tools.local_research.ai_status import run
    except ImportError:
        return result
    if os.getenv("CYBERBOT_AI_PANEL_ENABLED") != "1":
        result["status"] = "disabled"
        return result
    try:
        # Same checkout only. No arbitrary file paths accepted from HTTP clients.
        data = run(Path(__file__).resolve().parent.parent)
        if data.get("version") != "ai-status-1" or any(data.get(key) is not False for key in ("real_orders", "automatic_promotion", "profitability_verified")):
            raise ValueError("Unexpected research authority")
        for name in AI_MODELS:
            row = data["models"][name]
            status = row.get("status")
            if status not in AI_STATES:
                status = "DATA_REVIEW_REQUIRED"
            count = row.get("observations_scored")
            result["models"][name] = {"status": status, "observations_scored": count if type(count) is int and count >= 0 else None}
        result["status"] = "research_inventory_available"
    except (OSError, RuntimeError, sqlite3.Error, ValueError, KeyError, TypeError, ArithmeticError, ImportError, AttributeError):
        result.update(status="unavailable", models={})
    return result


@router.get("/api/integration/ai")
def research_status():
    return ai_status()

def notification_status(path=None, *, now=None):
    """Read only the notification worker health handoff, not push credentials or inbox."""
    result = {"status": "not_configured", "last_cycle_utc": None,
              "device_delivery_verified": False, "news_delivery_verified": False}
    path = path or os.getenv("CYBERBOT_NOTIFICATION_HEALTH_FILE")
    if not path:
        return result
    try:
        import json
        with Path(path).open("rb") as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise ValueError("Health report too large")
        report = json.loads(raw)
        stamp = datetime.fromisoformat(report["finished_at"])
        start = datetime.fromisoformat(report["started_at"])
        clock = now or datetime.now(timezone.utc)
        if stamp.tzinfo is None or start.tzinfo is None or not start <= stamp <= clock:
            raise ValueError("Invalid worker timestamps")
        state = report["status"]
        if state not in ("ok", "degraded", "error", "disabled", "unknown"):
            raise ValueError("Unknown health state")
        result.update(status="stale" if (clock-stamp).total_seconds() > 900 else state,
                      last_cycle_utc=stamp.astimezone(timezone.utc).isoformat())
    except FileNotFoundError:
        result["status"] = "not_available"
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        result["status"] = "unavailable"
    return result


@router.get("/api/integration/notifications")
def notifications_status():
    return notification_status()
