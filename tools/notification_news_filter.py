"""Pure news selection; does not suppress critical system or risk alerts."""
MARKETS = {"NASDAQ","BIST","XETRA","BINANCE_FUTURES","SOLANA","GLOBAL"}
PRIORITY = {"low":0,"medium":1,"high":2}

def matches_news(article, *, markets=(), symbols=(), topics=(), minimum="low", include_global=True):
    if minimum not in PRIORITY or any(m not in MARKETS for m in markets):
        raise ValueError("Invalid filter")
    market = article.get("market")
    priority = article.get("priority")
    if market not in MARKETS or priority not in PRIORITY:
        return False
    if PRIORITY[priority] < PRIORITY[minimum]:
        return False
    global_item = market == "GLOBAL"
    if global_item and not include_global:
        return False
    if markets and market not in markets and not global_item:
        return False
    if topics and not set(topics).intersection(article.get("topics", ())):
        return False
    if symbols and not global_item:
        wanted = {s.strip().upper() for s in symbols}
        actual = {s.strip().upper() for s in article.get("symbols", ())}
        if not wanted.intersection(actual):
            return False
    return True
