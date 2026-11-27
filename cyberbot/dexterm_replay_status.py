"""Read-only DexTerm historical position-replay handoff, never an observed/live ledger."""
import json
import os
from pathlib import Path

SCALE = 1_000_000
MAX_BYTES = 4 * 1024 * 1024
FALSE_FLAGS = ("security_verified", "live_data_verified", "pilot_applied", "real_orders",
               "route_integrity_verified", "depth_verified", "profitability_verified",
               "execution_verified", "strategy_evaluated", "real_fills",
               "intraperiod_risk_verified", "loss_budget_is_guaranteed",
               "quote_source_timestamp_verified", "fee_semantics_verified",
               "portfolio_mark_to_market_verified")


def integer(value, *, signed=False):
    if type(value) is not int or not (-10**18 if signed else 0) <= value <= 10**18:
        raise ValueError("Invalid replay integer")
    return value


def usdc(value):
    if value is None:
        return None
    sign = "-" if value < 0 else ""
    whole, fraction = divmod(abs(value), SCALE)
    return f"{sign}{whole}.{fraction:06d}"


def summarize(report):
    if not isinstance(report, dict) or report.get("status") not in ("position_replay_complete", "no_position_observations"):
        raise ValueError("Invalid replay status")
    if any(report.get(k) is not True for k in ("research_only", "paper_position_replay_only")) or any(report.get(k) is not False for k in (*FALSE_FLAGS, "network_requests")):
        raise ValueError("Unexpected replay authority")
    starting = integer(report["initial_balance_raw"])
    cash = integer(report["available_cash_raw"])
    cost = integer(report["open_cost_basis_raw"])
    realized = integer(report["realized_net_raw"], signed=True)
    closed = report["closed"]
    opened = report["open"]
    if not isinstance(closed, list) or not isinstance(opened, list) or len(closed) > 500 or len(opened) > 10:
        raise ValueError("Invalid replay position count")
    closed_count = integer(report["closed_positions"])
    open_count = integer(report["open_positions"])
    wins = integer(report["positive_closed_positions"])
    if closed_count != len(closed) or open_count != len(opened):
        raise ValueError("Replay position count mismatch")
    pnls = [integer(row["realized_net_raw"], signed=True) for row in closed]
    if sum(pnls) != realized or wins != sum(p > 0 for p in pnls):
        raise ValueError("Replay realized P/L mismatch")
    if sum(integer(row["entry_total_raw"]) for row in opened) != cost or any(row["market_value_raw"] is not None for row in opened):
        raise ValueError("Unexpected open position valuation")
    if starting <= 0 or cash + cost != starting + realized:
        raise ValueError("Replay cash accounting mismatch")
    final = report["final_equity_raw"]
    unrealized = report["unrealized_net_raw"]
    if opened:
        if final is not None or unrealized is not None:
            raise ValueError("Unverified open valuation")
    elif integer(final) != cash or integer(unrealized) != 0:
        raise ValueError("Closed replay valuation mismatch")
    if (report["status"] == "no_position_observations") != (not opened and not closed):
        raise ValueError("Replay status mismatch")
    if type(report["entry_halted"]) is not bool or type(report["risk_mode"]) is not bool:
        raise ValueError("Invalid replay risk fields")
    gross_loss = integer(report["gross_realized_loss_raw"])
    if gross_loss != sum(max(0, -p) for p in pnls):
        raise ValueError("Replay loss mismatch")
    return {"status": report["status"], "mode": "historical_replay_only", "currency": "USDC",
            "initial_balance": usdc(starting), "cash": usdc(cash), "open_cost_basis": usdc(cost),
            "realized_pnl": usdc(realized), "final_equity": usdc(final),
            "closed_positions": closed_count, "open_positions": open_count,
            "positive_closed_positions": wins, "gross_realized_loss": usdc(gross_loss),
            "replay_risk_mode": report["risk_mode"], "replay_entry_halted": report["entry_halted"],
            "freshness_verified": False, "live_data_verified": False,
            "paper_execution_verified": False, "real_orders": False}


def read(path=None):
    base = {"status": "not_configured", "mode": "historical_replay_only", "currency": "USDC",
            "live_data_verified": False, "paper_execution_verified": False, "real_orders": False,
            "freshness_verified": False}
    path = path or os.getenv("CYBERBOT_DEXTERM_REPLAY_REPORT")
    if not path:
        return base
    try:
        file = Path(path)
        if not file.is_file():
            return {**base, "status": "report_missing"}
        with file.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Report too large")
        return summarize(json.loads(raw.decode("utf-8-sig")))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
        return {**base, "status": "report_unavailable"}
