"""Read-only Solana quote diagnostics, never an executable pilot quote."""
import os,json,re
from decimal import Decimal as D
import httpx
from .. import solana_pilot as sol
from ..observed_pilot import PilotError,utc
RPC="https://api.mainnet-beta.solana.com"
RPC_ENDPOINTS={"official":RPC,"publicnode":"https://solana-rpc.publicnode.com"}
def rpc_endpoint():
    name=os.getenv("CYBERBOT_SOLANA_RPC_PROVIDER","official")
    if name not in RPC_ENDPOINTS:raise PilotError("RPC provider not allowed")
    return name,RPC_ENDPOINTS[name]
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
def owner_sample(largest,raw,info,mint):
    """Group the bounded largest-account sample by token-account authority.
    Authorities may be vaults, PDAs or custodians, not individual wallets.
    """
    concentration(largest,info)
    prior_slot,accounts=rpc_result(largest)
    slot,rows=rpc_result(raw)
    if not prior_slot<=slot<=prior_slot+20 or abs(slot-info["slot"])>20:
        raise PilotError("Token hesap sahibi slot uyumsuz.")
    if not isinstance(rows,list) or len(rows)!=len(accounts):
        raise PilotError("Token hesap sahibi örneklemi eksik.")
    grouped={}
    for account,row in zip(accounts,rows):
        if not isinstance(row,dict) or row.get("owner")!=LEGACY or row.get("executable") is not False:
            raise PilotError("Token hesap programı geçersiz.")
        data=row["data"]
        parsed=data["parsed"]
        if data.get("program")!="spl-token" or parsed.get("type")!="account":
            raise PilotError("Token hesap türü geçersiz.")
        item=parsed["info"]
        owner=item.get("owner")
        balance=item["tokenAmount"]
        amount=uint(balance.get("amount"))
        if (item.get("mint")!=mint or not sol.address(owner) or
            type(balance.get("decimals")) is not int or balance["decimals"]!=info["decimals"] or
            amount!=uint(account["amount"]) or item.get("state") not in ("initialized","frozen")):
            raise PilotError("Token hesap kimliği veya bakiyesi değişti.")
        grouped[owner]=grouped.get(owner,0)+amount
    balances=sorted(grouped.values(),reverse=True)
    def pct(amount):return str(D(amount)*100/D(info["supply"]))
    return {"status":"sampled_authorities_only","slot":slot,
            "sampled_accounts":len(accounts),"sampled_authorities":len(grouped),
            "sample_supply_pct":pct(sum(balances)),
            "largest_sampled_authority_pct_of_supply":pct(balances[0]),
            "top10_sampled_authorities_pct_of_supply":pct(sum(balances[:10])),
            "sampled_top10_above_30pct":D(pct(sum(balances[:10])))>D(30),
            "beneficial_ownership_verified":False,"wallet_concentration_verified":False,
            "pool_vaults_excluded":False,"security_verified":False,
            "trade_eligible":False,"pilot_applied":False,"real_orders":False}
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
def request(client,kind,params,key,*,rpc_url=None):
    if kind=="rpc":
        method,args=params
        if method not in ("getAccountInfo","getTokenLargestAccounts","getMultipleAccounts"):raise PilotError("RPC metodu izinli değil.")
        url=rpc_endpoint()[1] if rpc_url is None else rpc_url
        if url not in RPC_ENDPOINTS.values():raise PilotError("RPC endpoint not allowed")
        method_http,url,kw="POST",url,{"json":{"jsonrpc":"2.0","id":1,"method":method,"params":args}}
    elif kind=="pool":
        if not sol.address(params):raise PilotError("Havuz kimliği geçersiz.")
        method_http,url,kw="GET",DEX+params,{}
    elif kind=="quote":
        method_http,url,kw="GET",JUP,{"params":params,"headers":{"x-api-key":key} if key else {}}
    else:raise PilotError("İzinsiz kaynak.")
    stage=("solana_rpc."+method if kind=="rpc" else "dexscreener.pool" if kind=="pool" else "jupiter.buy" if params.get("inputMint")==USDC else "jupiter.sell")
    try:
        with client.stream(method_http,url,**kw) as res:
            res.raise_for_status();data=bytearray()
            for chunk in res.iter_bytes():
                data.extend(chunk)
                if len(data)>MAX_BYTES:raise PilotError(stage+": response_too_large")
        raw=json.loads(data)
    except httpx.HTTPStatusError as e:
        raise PilotError(stage+": HTTP "+str(e.response.status_code)+"; no_retry") from None
    except httpx.RequestError as e:
        raise PilotError(stage+": "+type(e).__name__+"; no_retry") from None
    except PilotError:raise
    except (ValueError,OSError) as e:
        raise PilotError(stage+": "+type(e).__name__+"; no_retry") from None
    if kind=="rpc" and isinstance(raw,dict) and "error" in raw:
        error=raw["error"]
        code=error.get("code") if isinstance(error,dict) else None
        raise PilotError(stage+": RPC "+str(code if type(code) is int else "unknown")+"; no_retry")
    return raw
def risk_screen(info,holders,pooldata,ask,bid):
    """Screen reported observations only; never authorize a pilot quote or fill."""
    liquidity=sol.number(pooldata["liquidity_usd_reported"])
    concentration_pct=sol.number(holders["top10_token_account_pct"],high="100")
    ask=sol.number(ask,low=".000000000001")
    bid=sol.number(bid,low=".000000000001")
    # Same-size indicative quotes, not independently verified executable depth.
    spread=(ask/bid-1)*100
    loss=(1-bid/ask)*100
    checks={
        "reported_liquidity_at_least_100k":liquidity>=D("100000"),
        "mint_authority_disabled":info["mint_authority_disabled"] is True,
        "freeze_authority_disabled":info["freeze_authority_disabled"] is True,
        "top10_token_accounts_at_most_30pct":concentration_pct<=D("30"),
        "indicative_spread_at_most_2pct":D(0)<=spread<=D("2"),
    }
    flags=[name for name,passed in checks.items() if not passed]
    return {"status":"reported_checks_passed_unverified" if not flags else "reported_risk_detected",
            "checks":checks,"failed_checks":flags,
            "indicative_spread_pct":str(spread),
            "indicative_roundtrip_loss_pct":str(loss),
            "execution_slippage_verified":False,"wallet_concentration_verified":False,
            "security_verified":False,"depth_verified":False,
            "trade_eligible":False,"pilot_applied":False,"real_orders":False}
def quote_ladder(samples,decimals):
    """Compare sequential same-pool round-trip quotes, not executable depth."""
    rows=[]
    reference_ask=reference_bid=None
    for size,tokens,received in samples:
        units=D(tokens)/D(10**decimals)
        ask=D(size)/units
        bid=D(received)/D(10**6)/units
        if reference_ask is None:reference_ask,reference_bid=ask,bid
        rows.append({"input_usdc":str(size),"quoted_tokens":str(units),
                     "indicative_ask_usdc":str(ask),"indicative_bid_usdc":str(bid),
                     "ask_change_vs_smallest_pct":str((ask/reference_ask-1)*100),
                     "bid_deterioration_vs_smallest_pct":str((1-bid/reference_bid)*100),
                     "roundtrip_loss_pct":str((1-D(received)/D(size*10**6))*100),
                     "crossed_quote":bid>ask})
    return {"status":"sequential_quotes_only","reference_input_usdc":rows[0]["input_usdc"],
            "samples":rows,"source_synchronization_verified":False,
            "execution_slippage_verified":False,"depth_verified":False,
            "trade_eligible":False,"pilot_applied":False,"real_orders":False}
def run(*,transport=None,clock=utc,depth_probe=False,owner_probe=False):
    if not configured():raise PilotError("Solana veri adaptörü veya kullanım izni/anahtarı eksik.")
    mint,pool=sol.config()
    if mint==USDC:raise PilotError("USDC baz token olamaz.")
    key=os.getenv("CYBERBOT_JUPITER_KEY","").strip()
    if key and (len(key)>256 or not re.fullmatch(r"[A-Za-z0-9_.-]+",key)):raise PilotError("API anahtarı biçimi geçersiz.")
    rpc_name,rpc_url=rpc_endpoint()
    started=clock()
    with httpx.Client(timeout=httpx.Timeout(8,connect=6),follow_redirects=False,trust_env=False) as c:
        def get(kind,params):return transport(kind,params) if transport else request(c,kind,params,key,rpc_url=rpc_url)
        info=mint_info(get("rpc",("getAccountInfo",[mint,{"encoding":"jsonParsed","commitment":"finalized"}])))
        largest=get("rpc",("getTokenLargestAccounts",[mint,{"commitment":"finalized"}]))
        holders=concentration(largest,info)
        owners=None
        if owner_probe:
            if not 0<=(clock()-started).total_seconds()<30:raise PilotError("Tanılama süresi aşıldı.")
            addresses=[item["address"] for item in rpc_result(largest)[1]]
            raw=get("rpc",("getMultipleAccounts",[addresses,{"encoding":"jsonParsed","commitment":"finalized","minContextSlot":holders["slot"]}]))
            owners=owner_sample(largest,raw,info,mint)
        pooldata=pool_info(get("pool",pool),mint,pool)
        def query(a,b,n):return quote(get("quote",{"inputMint":a,"outputMint":b,"amount":str(n)}),a,b,n,pool)
        samples=[]
        for size in ((25,50,100) if depth_probe else (100,)):
            if not 0<=(clock()-started).total_seconds()<30:raise PilotError("Tanılama süresi aşıldı.")
            tokens=query(USDC,mint,size*10**6)
            if not 0<=(clock()-started).total_seconds()<30:raise PilotError("Tanılama süresi aşıldı.")
            received=query(mint,USDC,tokens)
            samples.append((size,tokens,received))
    elapsed=(clock()-started).total_seconds()
    if not 0<=elapsed<=30:raise PilotError("Tanılama süresi aşıldı.")
    units=D(tokens)/D(10**info["decimals"])
    ask=D(100)/units;bid=(D(received)/D(10**6))/units
    return {"status":"diagnostic_only","mint":mint,"pool":pool,"retrieved_at":clock().isoformat(),"quote_currency":"USDC","test_input_usdc":"100","quoted_tokens":str(units),"quoted_return_usdc":str(D(received)/D(10**6)),"indicative_ask_usdc":str(ask),"indicative_bid_usdc":str(bid),"roundtrip_indicative_pct":str((D(received)/D(AMOUNT)-1)*100),"pool":pooldata,"mint_checks":{**info,**holders},"risk_screen":risk_screen(info,holders,pooldata,ask,bid),"depth_probe":quote_ladder(samples,info["decimals"]) if depth_probe else None,"owner_probe":owners,"quote_source_timestamp_verified":False,"usd_conversion_verified":False,"security_verified":False,"depth_verified":False,"pilot_applied":False,"live_data_verified":False,"real_orders":False,"transport_mocked":transport is not None,"api_key_used":bool(key),"rpc_provider":rpc_name,"blockers":["USDC/USD dönüşümü yok","Kaynak zaman damgası ve eşzamanlılık doğrulanmadı","Token hesabı yoğunlaşması cüzdan yoğunlaşması değildir","Kotasyon dolum ve derinlik garantisi değildir"]}
