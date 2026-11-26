"""Research-only feed ingestion. Feed URLs must be operator-configured."""
import hashlib
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

MAX_BYTES = 2_000_000
ATOM = "{http://www.w3.org/2005/Atom}"

def clean(value):
    return " ".join(re.sub(r"<[^>]*>", " ", value or "").split())

def ingest_feed(store, payload, source, allowed_hosts, max_items=100):
    """Parse already-fetched bytes; never fetch URLs or execute feed content."""
    if not isinstance(payload, bytes) or len(payload) > MAX_BYTES:
        raise ValueError("Invalid feed size")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("DTD prohibited")
    if not 1 <= max_items <= 500:
        raise ValueError("Invalid item limit")
    root = ET.fromstring(payload)
    entries = root.findall("./channel/item") if root.tag == "rss" else root.findall(ATOM + "entry")
    result = {"seen": 0, "published": 0, "rejected": 0, "duplicates": 0}
    hosts = {h.lower() for h in allowed_hosts}
    for entry in entries[:max_items]:
        result["seen"] += 1
        atom = entry.tag == ATOM + "entry"
        title = clean(entry.findtext(ATOM + "title" if atom else "title"))
        link_node = entry.find(ATOM + "link") if atom else None
        link = link_node.get("href", "") if link_node is not None else (entry.findtext("link") or "")
        try:
            url = urlsplit(link)
            valid = url.scheme == "https" and url.hostname in hosts and not url.username and not url.password and url.port in (None, 443)
        except ValueError:
            valid = False
        if not title or not valid:
            result["rejected"] += 1
            continue
        summary = clean(entry.findtext(ATOM + "summary" if atom else "description"))[:1500]
        date = entry.findtext(ATOM + "published" if atom else "pubDate") or entry.findtext(ATOM + "updated") or ""
        try:
            dt = datetime.fromisoformat(date.replace("Z", "+00:00")) if atom else parsedate_to_datetime(date)
            published = dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else "unknown"
        except (ValueError, TypeError, OverflowError):
            published = "unknown"
        canonical = url._replace(fragment="", query="").geturl()
        key = "news:" + hashlib.sha256(canonical.encode()).hexdigest()
        body = f"{summary or title}\nYayın: {published}\nKaynak: {link}\nİçerik bağımsız doğrulanmadı."
        added = store.publish(key, "news", "info", title[:300], body, source)
        result["published" if added else "duplicates"] += 1
    return result
