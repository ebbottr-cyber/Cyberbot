"""Structured BIST disclosure adapter; upstream acquisition is separate."""
import hashlib
import re
from datetime import datetime
from urllib.parse import urlsplit

HOSTS = {"KAP": {"kap.org.tr", "www.kap.org.tr"}, "TCMB": {"tcmb.gov.tr", "www.tcmb.gov.tr"}}
TOPICS = {"financial_results", "dividend", "capital_change", "interest_rate", "disclosure"}

def ingest_disclosure(store, *, source, disclosure_id, title, published_at, url, topic, symbols=(), enabled=False):
    if not enabled:
        return False
    if source not in HOSTS or topic not in TOPICS:
        raise ValueError("Unsupported source or topic")
    link = urlsplit(url)
    if link.scheme != "https" or link.hostname not in HOSTS[source] or link.username or link.password or link.port not in (None,443):
        raise ValueError("Official HTTPS link required")
    stamp = datetime.fromisoformat(published_at)
    if stamp.tzinfo is None:
        raise ValueError("Timezone required")
    if not isinstance(disclosure_id,str) or not disclosure_id.strip() or len(disclosure_id)>200:
        raise ValueError("Disclosure ID required")
    if not isinstance(title,str) or not title.strip() or len(title)>300:
        raise ValueError("Invalid title")
    if isinstance(symbols,str) or len(symbols)>100 or any(not isinstance(s,str) or not re.fullmatch(r"[A-Z0-9]{1,12}",s) for s in symbols):
        raise ValueError("Invalid symbols")
    key = hashlib.sha256((source+":"+disclosure_id).encode()).hexdigest()
    severity = "warning" if topic == "interest_rate" else "info"
    body = f"Kaynak: {source}\nYayın: {stamp.isoformat()}\nSemboller: {', '.join(symbols)}\nKonu: {topic}\n{url}\nİçerik bağımsız doğrulanmadı; yalnızca araştırma."
    return store.publish("bist:"+key,"news",severity,title.strip(),body,source)
