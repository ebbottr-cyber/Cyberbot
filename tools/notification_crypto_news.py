"""Opt-in structured crypto announcements; no network or execution side effects."""
import hashlib
import re
from datetime import datetime
from urllib.parse import urlsplit

HOSTS = {
    "BINANCE_FUTURES": {"www.binance.com", "binance.com"},
    "SOLANA": {"solana.com", "www.solana.com", "status.solana.com"},
}
TOPICS = {"listing", "delisting", "maintenance", "network_outage", "security", "funding_change", "recovery"}

def ingest_announcement(store, *, market, announcement_id, title, published_at, url, topic, symbols=(), enabled=False):
    if not enabled:
        return False
    if market not in HOSTS or topic not in TOPICS:
        raise ValueError("Unsupported market or topic")
    link = urlsplit(url)
    if link.scheme != "https" or link.hostname not in HOSTS[market] or link.username or link.password or link.port not in (None,443):
        raise ValueError("Official HTTPS link required")
    stamp = datetime.fromisoformat(published_at)
    if stamp.tzinfo is None:
        raise ValueError("Timezone required")
    if not isinstance(announcement_id,str) or not announcement_id.strip() or len(announcement_id)>200:
        raise ValueError("Announcement ID required")
    if not isinstance(title,str) or not title.strip() or len(title)>300:
        raise ValueError("Invalid title")
    if isinstance(symbols,str) or len(symbols)>100 or any(not isinstance(s,str) or not re.fullmatch(r"[A-Z0-9]{1,24}",s) for s in symbols):
        raise ValueError("Invalid symbols")
    key = hashlib.sha256((market+":"+announcement_id).encode()).hexdigest()
    severity = "warning" if topic in {"delisting","network_outage","security","maintenance","funding_change"} else "info"
    body = f"Piyasa: {market}\nYayın: {stamp.isoformat()}\nSemboller: {', '.join(symbols)}\nKonu: {topic}\n{url}\nİçerik bağımsız doğrulanmadı; yalnızca araştırma."
    return store.publish("crypto-news:"+key,"news",severity,title.strip(),body,market)
