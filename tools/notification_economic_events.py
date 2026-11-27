"""Normalize economic calendar records; no live fetch or trading."""
from urllib.parse import urlsplit
from tools.notification_calendar import aware

SOURCES = {
    "FED": ("federalreserve.gov", "www.federalreserve.gov"),
    "TCMB": ("tcmb.gov.tr", "www.tcmb.gov.tr"),
    "ECB": ("ecb.europa.eu", "www.ecb.europa.eu"),
    "BLS": ("bls.gov", "www.bls.gov"),
    "BEA": ("bea.gov", "www.bea.gov"),
    "TUIK": ("tuik.gov.tr", "www.tuik.gov.tr", "data.tuik.gov.tr"),
    "EUROSTAT": ("ec.europa.eu",),
}
TYPES = {"rate_decision", "inflation", "employment", "gdp", "central_bank_minutes"}
MARKETS = {"NASDAQ", "BIST", "XETRA", "BINANCE_FUTURES", "SOLANA", "GLOBAL"}

def normalize_event(record, *, operator_verified=False):
    source = record["source"]
    if source not in SOURCES or record["type"] not in TYPES or record["market"] not in MARKETS:
        raise ValueError("Unsupported economic event")
    url = urlsplit(record["url"])
    if url.scheme != "https" or url.hostname not in SOURCES[source] or url.username or url.password or url.port not in (None,443):
        raise ValueError("Official HTTPS source required")
    for field in ("id", "title"):
        if not isinstance(record[field], str) or not record[field].strip() or len(record[field]) > 300:
            raise ValueError("Invalid event field")
    importance = record.get("importance", "medium")
    cancelled = record.get("cancelled", False)
    if importance not in {"low","medium","high"} or type(cancelled) is not bool:
        raise ValueError("Invalid event status")
    return {"id": record["id"], "title": record["title"], "source": source,
            "market": record["market"], "scheduled_at": aware(record["scheduled_at"]).isoformat(),
            "importance": importance, "cancelled": cancelled, "verified": operator_verified is True,
            "url": record["url"], "type": record["type"]}
