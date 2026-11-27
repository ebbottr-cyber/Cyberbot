"""Read-only Solana quote diagnostics, never an executable pilot quote."""
import os,json,re
from decimal import Decimal as D
import httpx
from .. import solana_pilot as sol
from ..observed_pilot import PilotError,utc
RPC="https://api.mainnet-beta.solana.com"
DEX="https://api.dexscreener.com/latest/dex/pairs/solana/"
JUP="https://api.jup.ag/swap/v2/order"
USDC="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
LEGACY="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
AMOUNT=100_000_000
MAX_BYTES=262144
def configured():
    return os.getenv("CYBERBOT_SOLANA_OBSERVED_ENABLED")=="1" and os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")=="1" and (bool(os.getenv("CYBERBOT_JUPITER_KEY","").strip()) or os.getenv("CYBERBOT_JUPITER_ANONYMOUS_ENABLED")=="1")
def uint(v,positive=False):
    if not isinstance(v,str) or not re.fullmatch(r"[0-9]{1,20}",v):raise PilotError("Ham token miktarı geçersiz.")
    n=int(v)
    if n>=2**64 or (positive and n==0):raise PilotError("Ham token miktarı sınırı.")
    return n
def rpc_result(d):
    if not isinstance(d,dict) or d.get("jsonrpc")!="2.0" or d.get("id")!=1 or "error" in d:raise PilotError("RPC yanıtı geçersiz.")
    x=d["result"];slot=x["context"]["slot"]
    if type(slot) is not int or slot<=0:raise PilotError("RPC slot geçersiz.")
    return slot,x["value"]
def mint_info(raw):
    slot,v=rpc_result(raw)
    if v["owner"]!=LEGACY or v.get("executable") is not False or v["data"]["program"]!="spl-token" or v["data"]["parsed"]["type"]!="mint":raise PilotError("Yalnız legacy SPL mint desteklenir.")
    i=v["data"]["parsed"]["info"];decimals=i["decimals"]
    if type(decimals) is not int or not 0<=decimals<=9 or i.get("isInitialized") is not True:raise PilotError("Mint bilgisi geçersiz.")
    return {"slot":slot,"decimals":decimals,"supply":uint(i["supply"],True),"mint_authority_disabled":"mintAuthority" in i and i["mintAuthority"] is None,"freeze_authority_disabled":"freezeAuthority" in i and i["freezeAuthority"] is None}
def concentration(raw,info):
    slot,rows=rpc_result(raw)
    if abs(slot-info["slot"])>20 or not isinstance(rows,list) or not 1<=len(rows)<=20:raise PilotError("Token hesap gözlemi uyumsuz.")
    seen=set();amounts=[]
    for x in rows:
        a=x["address"]
        if not sol.address(a) or a in seen or x["decimals"]!=info["decimals"]:raise PilotError("Token hesap kimliği geçersiz.")
        seen.add(a);amounts.append(uint(x["amount"]))
    if amounts!=sorted(amounts,reverse=True) or sum(amounts)>info["supply"]:raise PilotError("Token hesap miktarı uyumsuz.")
    return {"slot":slot,"top10_token_account_pct":str(D(sum(amounts[:10]))*100/D(info["supply"])),"wallet_concentration_verified":False}
def pool_info(raw,mint,pool):
    pairs=raw.get("pairs")
    if not isinstance(pairs,list):raise PilotError("DEX havuz verisi eksik.")
    rows=[p for p in pairs if p.get("chainId")=="solana" and p.get("pairAddress")==pool and p.get("baseToken",{}).get("address")==mint and p.get("quoteToken",{}).get("address")==USDC]
    if len(rows)!=1:raise PilotError("Seçilen doğrudan USDC havuzu bulunamadı.")
    x=rows[0];return {"liquidity_usd_reported":str(sol.number(x["liquidity"]["usd"])),"spot_usd_reported":str(sol.number(x["priceUsd"],low=".000000000001")),"source_timestamp_verified":False}
def quote(raw,inp,out,amount,pool):
    if raw.get("error") or raw.get("errorCode") not in (None,0) or raw.get("transaction") not in (None,"") or raw.get("taker") not in (None,""):raise PilotError("Yalnız cüzdansız kotasyon kabul edilir.")
    if (raw.get("inputMint"),raw.get("outputMint"),raw.get("swapMode"))!=(inp,out,"ExactIn") or uint(raw.get("inAmount"),True)!=amount:raise PilotError("Kotasyon kimliği/miktarı uyuşmuyor.")
    n=uint(raw.get("outAmount"),True);routes=raw.get("routePlan")
    if not isinstance(routes,list) or len(routes)!=1:raise PilotError("Tek havuzlu rota gerekli.")
    route=routes[0];s=route["swapInfo"]
    if (s.get("ammKey"),s.get("inputMint"),s.get("outputMint"))!=(pool,inp,out) or uint(s["inAmount"],True)!=amount:raise PilotError("Kotasyon farklı havuz veya miktar kullanıyor.")
    gross=uint(s["outAmount"],True)
    if gross!=n:
        # Only accept a bounded, declared fee gap in diagnostic mode.
        # This does not establish the provider's fee accounting semantics.
        bps=raw.get("feeBps");fee=raw.get("platformFee")
        if type(bps) is not int or not 1<=bps<=100 or not isinstance(fee,dict) or fee.get("feeBps")!=bps or raw.get("feeMint") not in (inp,out) or fee.get("feeMint")!=raw.get("feeMint") or not 0<gross-n<=(gross*bps+9999)//10000:
            raise PilotError("Net rota miktarı doğrulanamadı.")
    if route.get("bps")!=10000 and route.get("percent")!=100:raise PilotError("Tam rota gerekli.")
    return n
def request(client,kind,params,key):
    if kind=="rpc":
        method,args=params
        if method not in ("getAccountInfo","getTokenLargestAccounts"):raise PilotError("RPC metodu izinli değil.")
        method_http,url,kw="POST",RPC,{"json":{"jsonrpc":"2.0","id":1,"method":method,"params":args}}
    elif kind=="pool":
        if not sol.address(params):raise PilotError("Havuz kimliği geçersiz.")
        method_http,url,kw="GET",DEX+params,{}
    elif kind=="quote":
        method_http,url,kw="GET",JUP,{"params":params,"headers":{"x-api-key":key} if key else {}}
    else:raise PilotError("İzinsiz kaynak.")
    try:
        with client.stream(method_http,url,**kw) as res:
            res.raise_for_status();data=bytearray()
            for chunk in res.iter_bytes():
                data.extend(chunk)
                if len(data)>MAX_BYTES:raise PilotError("Kaynak yanıt sınırı.")
        return json.loads(data)
    except (httpx.HTTPError,ValueError,OSError):raise PilotError("Salt okunur sağlayıcı sorgusu başarısız; tekrar yok.") from None
def run(*,transport=None,clock=utc):
    if not configured():raise PilotError("Solana veri adaptörü veya kullanım izni/anahtarı eksik.")
    mint,pool=sol.config()
    if mint==USDC:raise PilotError("USDC baz token olamaz.")
    key=os.getenv("CYBERBOT_JUPITER_KEY","").strip()
    if key and (len(key)>256 or not re.fullmatch(r"[A-Za-z0-9_.-]+",key)):raise PilotError("API anahtarı biçimi geçersiz.")
    started=clock()
    with httpx.Client(timeout=httpx.Timeout(8,connect=3),follow_redirects=False,trust_env=False) as c:
        def get(kind,params):return transport(kind,params) if transport else request(c,kind,params,key)
        info=mint_info(get("rpc",("getAccountInfo",[mint,{"encoding":"jsonParsed","commitment":"finalized"}])))
        holders=concentration(get("rpc",("getTokenLargestAccounts",[mint,{"commitment":"finalized"}])),info)
        pooldata=pool_info(get("pool",pool),mint,pool)
        def query(a,b,n):return quote(get("quote",{"inputMint":a,"outputMint":b,"amount":str(n)}),a,b,n,pool)
        tokens=query(USDC,mint,AMOUNT)
        received=query(mint,USDC,tokens)
    elapsed=(clock()-started).total_seconds()
    if not 0<=elapsed<=30:raise PilotError("Tanılama süresi aşıldı.")
    units=D(tokens)/D(10**info["decimals"])
    ask=D(100)/units;bid=(D(received)/D(10**6))/units
    return {"status":"diagnostic_only","mint":mint,"pool":pool,"retrieved_at":clock().isoformat(),"quote_currency":"USDC","test_input_usdc":"100","quoted_tokens":str(units),"quoted_return_usdc":str(D(received)/D(10**6)),"indicative_ask_usdc":str(ask),"indicative_bid_usdc":str(bid),"roundtrip_indicative_pct":str((D(received)/D(AMOUNT)-1)*100),"pool":pooldata,"mint_checks":{**info,**holders},"quote_source_timestamp_verified":False,"usd_conversion_verified":False,"security_verified":False,"depth_verified":False,"pilot_applied":False,"live_data_verified":False,"real_orders":False,"transport_mocked":transport is not None,"api_key_used":bool(key),"blockers":["USDC/USD dönüşümü yok","Kaynak zaman damgası ve eşzamanlılık doğrulanmadı","Token hesabı yoğunlaşması cüzdan yoğunlaşması değildir","Kotasyon dolum ve derinlik garantisi değildir"]}
