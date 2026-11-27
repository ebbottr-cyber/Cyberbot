"""Bounded public pool discovery, read-only. Candidates are not verified memes or trade signals."""
import json,os
from decimal import Decimal,InvalidOperation
from urllib.parse import urlencode
import httpx
from cyberbot.solana_pilot import address
from cyberbot.providers.solana_observed import USDC

LIMIT=Decimal("100000")
MAX_BYTES=2_000_000
GECKO="https://api.geckoterminal.com/api/v2/networks/solana/"
DEX="https://api.dexscreener.com/latest/dex/search?"
# Known search labels for technical coverage only; not a recommendation or mint verification.
QUERIES=("BONK/USDC","WIF/USDC","POPCAT/USDC","PENGU/USDC")
def fetch(client,url):
    with client.stream("GET",url) as res:
        res.raise_for_status();data=bytearray()
        for chunk in res.iter_bytes():
            data.extend(chunk)
            if len(data)>MAX_BYTES:raise ValueError("response too large")
    return json.loads(data)
def gecko_rows(raw):
    for p in raw["data"]:
        a=p["attributes"];rel=p["relationships"]
        base=rel["base_token"]["data"]["id"];quote=rel["quote_token"]["data"]["id"]
        if not all(isinstance(x,str) and x.startswith("solana_") for x in (base,quote,p["id"])):continue
        yield base[7:],quote[7:],p["id"][7:],a.get("reserve_in_usd"),a.get("name",""),"geckoterminal"
def dex_rows(raw):
    for p in raw["pairs"]:
        if p.get("chainId")!="solana":continue
        yield p["baseToken"]["address"],p["quoteToken"]["address"],p["pairAddress"],(p.get("liquidity") or {}).get("usd"),p["baseToken"].get("symbol",""),"dexscreener"
def candidates(rows):
    pools={}
    for mint,quote,pool,liq,label,source in rows:
        if quote!=USDC or not address(mint) or not address(pool) or mint in (USDC,pool):continue
        try:v=Decimal(str(liq))
        except (InvalidOperation,ValueError):continue
        if not v.is_finite() or v<LIMIT or v>Decimal("1000000000000"):continue
        key=(mint,pool)
        if key not in pools:pools[key]={"mint":mint,"pool":pool,"label":str(label)[:80],"reported_liquidity_usd":str(v),"sources":[source],"security_verified":False}
        else:
            p=pools[key]
            p["reported_liquidity_usd"]=str(min(Decimal(p["reported_liquidity_usd"]),v))
            if source not in p["sources"]:p["sources"].append(source)
    return sorted(pools.values(),key=lambda p:Decimal(p["reported_liquidity_usd"]),reverse=True)[:20]
def main():
    if os.getenv("CYBERBOT_SOLANA_READ_ENABLED")!="1" or os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        print(json.dumps({"status":"disabled","reason":"explicit data rights and read flag required"}));return 1
    rows=[];errors={}
    sources=[("top",GECKO+"pools?page=1",gecko_rows),("trending",GECKO+"trending_pools?page=1",gecko_rows)]
    sources += [(q,DEX+urlencode({"q":q}),dex_rows) for q in QUERIES]
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as c:
        for name,url,parse in sources:
            try:rows.extend(list(parse(fetch(c,url))))
            except (httpx.HTTPError,ValueError,KeyError,TypeError,AttributeError) as e:errors[name]=type(e).__name__
    result=candidates(rows)
    print(json.dumps({"status":"discovery_only","queries":len(sources),"rows":len(rows),"candidates":result,"errors":errors,"meme_classification_verified":False,"security_verified":False,"live_data_verified":False,"real_orders":False,"pilot_applied":False},ensure_ascii=True))
    return 0 if len(errors)<len(sources) else 1
if __name__=="__main__":raise SystemExit(main())
