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
        result["market_memory"] = memory_summary(data.get("market_memory", {}))
        result["status"] = "research_inventory_available"
    except (OSError, RuntimeError, sqlite3.Error, ValueError, KeyError, TypeError, ArithmeticError, ImportError, AttributeError):
        result.update(status="unavailable", models={}, market_memory=[])
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

from .pilot_performance import snapshot as pilot_performance_snapshot
from .pilot_control import snapshot as pilot_control_snapshot
from .dexterm_replay_status import read as dexterm_replay_status

OBSERVED_MARKETS = ("BIST", "NASDAQ", "XETRA", "FUTURES")
PORTFOLIO_FIELDS = ("equity", "cash", "daily_pnl", "current_drawdown_pct", "position_open", "risk_gate")
STAT_FIELDS = ("closed", "wins", "losses", "realized_pnl", "win_pct", "nominal_fees", "liquidations")
CURRENCIES = {"BIST": "TRY", "NASDAQ": "USD", "XETRA": "USD", "FUTURES": "USDT", "SOLANA": "USDC"}


def portfolio_risk_status():
    """Report independent observed accounts; never merge demo, replay and observed balances."""
    result = {"version": "central-portfolio-1", "mode": "operator_observed_unverified",
              "as_of": None, "markets": [], "entry_halted": None,
              "combined_equity": None, "real_orders": False, "automatic_entry_enabled": False,
              "live_data_verified": False, "profitability_verified": False,
              "cross_source_atomic_snapshot": False}
    try:
        data = pilot_performance_snapshot(markets=OBSERVED_MARKETS)
        if data.get("mode") != result["mode"] or data.get("real_orders") is not False:
            raise ValueError("Unexpected portfolio authority")
        rows = {r["market"]: r for r in data["markets"]}
        result["as_of"] = data["as_of"]
    except (OSError, RuntimeError, sqlite3.Error, ValueError, KeyError, TypeError, ArithmeticError):
        rows = {}
    try:
        value = pilot_control_snapshot()["halted"]
        if type(value) is bool:
            result["entry_halted"] = value
    except (OSError, RuntimeError, sqlite3.Error, ValueError, KeyError, TypeError, ArithmeticError):
        pass
    for market in MARKETS:
        item = {"market": market, "currency": CURRENCIES[market], "status": "unavailable",
                "source": "observed_pilot", "statistics": None, **dict.fromkeys(PORTFOLIO_FIELDS)}
        if market == "SOLANA":
            item.update(source="DexTerm", status="dexterm_portfolio_not_connected", historical_replay=dexterm_replay_status())
        elif market in rows:
            row = rows[market]
            if row.get("currency") == item["currency"]:
                item.update(status=row.get("status", "unavailable"))
                if item["status"] in ("recorded", "valuation_unavailable"):
                    item.update({k: row.get(k) for k in PORTFOLIO_FIELDS})
                    stats = row.get("statistics")
                    if isinstance(stats, dict):
                        item["statistics"] = {k: stats.get(k) for k in STAT_FIELDS}
                    if item["status"] != "recorded":
                        item.update(equity=None, daily_pnl=None, current_drawdown_pct=None, risk_gate=None)
                    if result["entry_halted"] is not False:
                        item["risk_gate"] = False if result["entry_halted"] is True else None
        result["markets"].append(item)
    return result


@router.get("/api/integration/portfolio")
def portfolio_status():
    return portfolio_risk_status()

MEMORY_STATES = {"NOT_INITIALIZED", "AWAITING_EVIDENCE", "RESEARCH_ONLY", "DATA_REVIEW_REQUIRED"}


def memory_summary(memory):
    rows = []
    for market in MARKETS:
        row = memory.get(market, {})
        state = row.get("status", "NOT_INITIALIZED")
        scopes = row.get("scopes", [])
        if state not in MEMORY_STATES or not isinstance(scopes, list) or len(scopes) > 10000:
            state, scopes = "DATA_REVIEW_REQUIRED", []
        counts = [s.get("reports") if isinstance(s, dict) else None for s in scopes]
        if any(type(n) is not int or not 1 <= n <= 10**12 for n in counts) or (state == "RESEARCH_ONLY") != bool(scopes):
            state, scopes, counts = "DATA_REVIEW_REQUIRED", [], []
        rows.append({"market": market, "status": state,
                     "scope_count": len(scopes) if state != "DATA_REVIEW_REQUIRED" else None,
                     "report_count": sum(counts) if state != "DATA_REVIEW_REQUIRED" else None})
    return rows


DETAIL_STATES = {
    "windows_health": {"NOT_AVAILABLE", "DATA_REVIEW_REQUIRED", "STALE", "REVIEW_REQUIRED", "NOT_FULLY_RUNNING", "SCHEDULER_OK"},
    "learning_cycle": {"WAIT_EVIDENCE", "DATA_REVIEW_REQUIRED", "WAIT_STORAGE", "INITIAL_COMPARISON_REVIEW", "WAIT_NEW_DATA", "WAIT_COOLDOWN", "RECOMPARISON_REVIEW"},
    "orchestrator": {"DATA_REVIEW_REQUIRED", "WAIT_STORAGE", "WAIT_LEARNING_REVIEW", "READY_FOR_PAIRED_RESEARCH"},
    "risk_referee": {"HUMAN_REVIEW_ONLY", "REVIEW_BLOCKED"},
    "decision_memory": {"NOT_AVAILABLE", "LIMIT_REACHED", "AVAILABLE", "DATA_REVIEW_REQUIRED"},
    "error_memory": {"NOT_AVAILABLE", "INSUFFICIENT_EVIDENCE", "RESEARCH_MEASURED", "DATA_REVIEW_REQUIRED"},
    "model_lifecycle": {"NOT_AVAILABLE", "LIMIT_REACHED", "AVAILABLE", "DATA_REVIEW_REQUIRED"},
}
FUTURES_SCOPE = "FUTURES/BTCUSDT/binance-usdm-public"


def ai_learning_status():
    """Manual read-only detailed research summary, without exposing raw records."""
    base = {"status": "disabled", "scope": FUTURES_SCOPE, "sections": {},
            "training_started": False, "automatic_promotion": False,
            "real_orders": False, "paper_readiness_verified": False}
    if os.getenv("CYBERBOT_AI_PANEL_ENABLED") != "1":
        return base
    try:
        from tools.local_research.ai_dashboard import snapshot
    except ImportError:
        return {**base, "status": "not_integrated"}
    try:
        data = snapshot(Path(__file__).resolve().parent.parent)
        if data.get("version") != "ai-dashboard-1" or any(data.get(k) is not False for k in ("paper_readiness_verified", "real_orders", "automatic_promotion")):
            raise ValueError("Unexpected AI authority")
        for key in ("learning_cycle", "risk_referee", "error_memory"):
            if data[key].get("scope") != FUTURES_SCOPE:
                raise ValueError("Unexpected AI scope")
        if data["learning_cycle"].get("training_started") is not False or data["orchestrator"].get("training_started") is not False:
            raise ValueError("Unexpected training state")
        sections = {}
        for key, allowed in DETAIL_STATES.items():
            row = data[key]
            state = row["status"]
            if state not in allowed:
                raise ValueError("Unknown AI state")
            fields = {"status": state}
            for name in ("train_samples", "test_samples", "new_retained_blocks", "total_records", "measured_records", "event_count"):
                value = row.get(name)
                if type(value) is int and 0 <= value <= 10**12:
                    fields[name] = value
            sections[key] = fields
        return {**base, "status": "research_summary_available", "sections": sections}
    except (OSError, RuntimeError, sqlite3.Error, ValueError, KeyError, TypeError, ArithmeticError, ImportError, AttributeError):
        return {**base, "status": "unavailable"}


@router.get("/api/integration/ai/learning")
def learning_status():
    return ai_learning_status()

from .notification_handoff import read_inbox, read_news, CATEGORIES, MARKETS as NEWS_MARKETS
from fastapi import HTTPException

@router.get("/api/integration/inbox")
def inbox(category: str = "ALL"):
    if category not in ("ALL", *CATEGORIES):
        raise HTTPException(422,"Geçersiz bildirim kategorisi.")
    return read_inbox(category=category)

@router.get("/api/integration/news")
def research_news(market: str = "ALL"):
    if market not in ("ALL", *NEWS_MARKETS):
        raise HTTPException(422,"Geçersiz haber piyasası.")
    return read_news(market=market)
