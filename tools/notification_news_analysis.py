"""Deterministic news triage baseline, not an AI prediction or trade signal."""
import re
import unicodedata

RULES = {
    "monetary_policy": ("interest rate", "rate decision", "faiz kararı", "monetary policy", "para politikası"),
    "earnings": ("earnings", "financial results", "bilanço", "finansal sonuç"),
    "market_disruption": ("trading halt", "market suspension", "işlem sırası kapat", "işlemler durdur"),
    "macro": ("inflation", "enflasyon", "unemployment", "işsizlik"),
}
SOURCE_MARKETS = {"FED": ("NASDAQ", "CRYPTO"), "SEC": ("NASDAQ",),
                  "ECB": ("XETRA",), "KAP": ("BIST",), "TCMB": ("BIST",)}

def normalize(text):
    return unicodedata.normalize("NFKC", text).casefold().replace("\u0307", "")

def analyze_news(title, summary, source, symbol_aliases=None):
    text = normalize(title + " " + summary)
    topics = [topic for topic, terms in RULES.items()
              if any(normalize(term) in text for term in terms)]
    symbols = []
    for symbol, aliases in (symbol_aliases or {}).items():
        if any(re.search(r"(?<!\w)" + re.escape(normalize(alias)) + r"(?!\w)", text)
               for alias in aliases if len(alias.strip()) >= 3):
            symbols.append(symbol)
    priority = "high" if "market_disruption" in topics or "monetary_policy" in topics else ("medium" if topics or symbols else "low")
    return {"method": "rule_based_v1", "priority": priority,
            "topics": topics, "candidate_markets": list(SOURCE_MARKETS.get(source.upper(), ())),
            "candidate_symbols": sorted(symbols), "direction": "unknown",
            "impact_verified": False, "content_verified": False,
            "research_only": True, "orders_enabled": False,
            "reason": "Keyword and source matching; requires independent verification."}
