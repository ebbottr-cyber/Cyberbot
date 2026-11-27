"""Explicit event adapter. Does not execute orders or inspect accounts."""
import hashlib
import re

EVENTS = {
    "paper_trade": ("trade", "info", "Sanal işlem"),
    "live_trade_confirmed": ("trade", "warning", "Doğrulanmış gerçek işlem"),
    "signal": ("market", "info", "Araştırma sinyali"),
    "ai_evaluation": ("ai", "info", "Yapay zekâ değerlendirmesi"),
    "risk_alert": ("risk", "critical", "Risk uyarısı"),
    "data_integrity_error": ("data", "critical", "Veri bütünlüğü hatası"),
    "data_progress": ("data", "info", "Veri ilerlemesi"),
    "github_test": ("github", "info", "GitHub test sonucu"),
    "worker_error": ("system", "warning", "Servis hatası"),
}
MARKETS = {"NASDAQ", "BIST", "XETRA", "BINANCE_FUTURES", "SOLANA", "SYSTEM"}

def publish_event(store, *, event_id, kind, market, summary, enabled=False, execution_verified=False):
    if not enabled:
        return False
    if kind not in EVENTS or market not in MARKETS:
        raise ValueError("Unknown event or market")
    if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", event_id):
        raise ValueError("Stable event identifier required")
    if not isinstance(summary, str) or not summary.strip() or len(summary)>500:
        raise ValueError("Short sanitized summary required")
    if kind == "live_trade_confirmed" and execution_verified is not True:
        raise ValueError("Execution confirmation required")
    category, severity, title = EVENTS[kind]
    key = hashlib.sha256(f"{market}:{kind}:{event_id}".encode()).hexdigest()
    # Caller must supply a sanitized summary without credentials or account identifiers.
    return store.publish("bot:"+key, category, severity, f"{market} | {title}", summary.strip(), "Cyberbot")
