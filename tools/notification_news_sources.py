"""Opt-in official feed polling; no scheduler or trading side effects."""
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit
from tools.notification_news import ingest_feed, MAX_BYTES

# Candidate official endpoints; validate availability before enabling.
SOURCES = {
    "fed": ("FED", "https://www.federalreserve.gov/feeds/press_all.xml", ("www.federalreserve.gov",)),
    "ecb": ("ECB", "https://www.ecb.europa.eu/rss/press.html", ("www.ecb.europa.eu",)),
    "sec": ("SEC", "https://www.sec.gov/news/pressreleases.rss", ("www.sec.gov",)),
}
PENDING_SOURCES = ("KAP", "TCMB", "Borsa Istanbul", "Deutsche Boerse", "Binance", "Solana", "BLS", "Eurostat", "TUIK")

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def poll_source(store, source_id, *, enabled=False, user_agent=None):
    if not enabled:
        return {"status": "disabled"}
    if source_id not in SOURCES:
        raise ValueError("Unknown source")
    if not user_agent or not user_agent.strip():
        raise ValueError("Operator contact user agent required")
    name, url, hosts = SOURCES[source_id]
    if urlsplit(url).scheme != "https":
        raise ValueError("HTTPS required")
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml", "Accept-Encoding": "identity"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            payload = response.read(MAX_BYTES + 1)
        return {"status": "ok", **ingest_feed(store, payload, name, hosts)}
    except (OSError, ValueError, SyntaxError) as exc:
        return {"status": "error", "error_type": type(exc).__name__}
