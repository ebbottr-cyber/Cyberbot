"""Read-only Solana quote diagnostics, never an executable pilot quote."""
import os,json,re
from decimal import Decimal as D
import httpx
from .. import solana_pilot as sol
from ..observed_pilot import PilotError,utc
RPC="https://api.mainnet-beta.solana.com"
RPC_ENDPOINTS={"official":RPC,"publicnode":"https://solana-rpc.publicnode.com","rpcnode":"https://public-solana-mainnet.rpcnode.dev"}
def rpc_endpoint():
    name=os.getenv("CYBERBOT_SOLANA_RPC_PROVIDER","official")
    if name not in RPC_ENDPOINTS:raise PilotError("RPC provider not allowed")
    return name,RPC_ENDPOINTS[name]
RUG="https://api.rugcheck.xyz/v1/tokens/"
GECKO="https://api.geckoterminal.com/api/v2/networks/solana/tokens/"
DEX="https://api.dexscreener.com/latest/dex/pairs/solana/"
JUP="https://api.jup.ag/swap/v2/order"
USDC="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
LEGACY="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
AMOUNT=100_000_000
MAX_BYTES=262144
RUG_MAX_BYTES=8*1024*1024
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
class SellQuoteRejected(PilotError):
    """HTTP 400 on a read-only sell quote; cause not established."""

class HolderPercentagesInvalid(PilotError):
    """Reported account percentages exceed the allowed total; no risk clearance."""

class UnsupportedMint(PilotError):
    """Well-shaped account that does not satisfy the legacy-only policy."""

def mint_info(raw):
    slot,v=rpc_result(raw)
    if not isinstance(v,dict) or not sol.address(v.get("owner")) or type(v.get("executable")) is not bool:
        raise PilotError("Mint account response invalid")
    data=v.get("data")
    # A recognized owner different from the required program is ineligible.
    # No safety claim is made about this account or its extensions.
    if v["owner"]!=LEGACY:
        raise UnsupportedMint("Yalnız legacy SPL mint desteklenir.")
    if not isinstance(data,dict) or not isinstance(data.get("program"),str) or not isinstance(data.get("parsed"),dict) or not isinstance(data["parsed"].get("type"),str):
        raise PilotError("Mint account response invalid")
    if v["executable"] or data["program"]!="spl-token" or data["parsed"]["type"]!="mint":
        raise UnsupportedMint("Yalnız legacy SPL mint desteklenir.")
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
def reported_holders(rug,gecko,mint):
    # Third-party reports are not an equivalent of finalized RPC account data.
    if rug.get("mint")!=mint or gecko["data"]["attributes"].get("address")!=mint:
        raise PilotError("Holder report mint mismatch")
    rows=rug.get("topHolders")
    if not isinstance(rows,list) or not 10<=len(rows)<=20:
        raise PilotError("Holder report incomplete")
    seen=set();pcts=[]
    for row in rows:
        addr=row.get("address")
        if not sol.address(addr) or addr in seen:raise PilotError("Invalid holder report account")
        seen.add(addr);pcts.append(sol.number(row.get("pct"),high="100"))
    if sum(pcts)>100:raise HolderPercentagesInvalid("Invalid holder report percentages")
    top=sum(sorted(pcts,reverse=True)[:10],D(0))
    g=gecko["data"]["attributes"]["holders"]
    pct=sol.number(g["distribution_percentage"]["top_10"],high="100")
    for n in (rug.get("totalHolders"),g.get("count")):
        if type(n) is not int or n<10:raise PilotError("Invalid holder report count")
    from ..observed_pilot import ts
    source_at=ts(g["last_updated"]).isoformat()
    return {"holder_source":"public_reports","rugcheck_reported_top10_account_pct":str(top),
            "geckoterminal_reported_top10_pct":str(pct),"reported_pct_difference":str(abs(top-pct)),
            "rugcheck_reported_holder_count":rug["totalHolders"],"geckoterminal_reported_holder_count":g["count"],
            "geckoterminal_holder_source_at":source_at,"holder_source_timestamp_verified":False,
            "token_account_concentration_verified":False,"wallet_concentration_verified":False}
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
        if method not in ("getAccountInfo","getTokenLargestAccounts"):raise PilotError("RPC metodu izinli değil.")
        url=rpc_endpoint()[1] if rpc_url is None else rpc_url
        if url not in RPC_ENDPOINTS.values():raise PilotError("RPC endpoint not allowed")
        method_http,url,kw="POST",url,{"json":{"jsonrpc":"2.0","id":1,"method":method,"params":args}}
    elif kind in ("rugcheck","gecko_holders"):
        if not sol.address(params):raise PilotError("Invalid holder report mint")
        method_http,url,kw="GET",(RUG+params+"/report" if kind=="rugcheck" else GECKO+params+"/info"),{}
    elif kind=="pool":
        if not sol.address(params):raise PilotError("Havuz kimliği geçersiz.")
        method_http,url,kw="GET",DEX+params,{}
    elif kind=="quote":
        method_http,url,kw="GET",JUP,{"params":params,"headers":{"x-api-key":key} if key else {}}
    else:raise PilotError("İzinsiz kaynak.")
    stage=("solana_rpc."+method if kind=="rpc" else kind if kind in ("rugcheck","gecko_holders") else "dexscreener.pool" if kind=="pool" else "jupiter.buy" if params.get("inputMint")==USDC else "jupiter.sell")
    limit=RUG_MAX_BYTES if kind=="rugcheck" else MAX_BYTES
    try:
        with client.stream(method_http,url,**kw) as res:
            if stage=="jupiter.sell" and res.status_code==400:
                # Read only a bounded diagnostic body. Never echo arbitrary provider text.
                error_data=bytearray()
                for chunk in res.iter_bytes(chunk_size=4096):
                    if len(error_data)+len(chunk)>8192:break
                    error_data.extend(chunk)
                try:err=json.loads(error_data)
                except (ValueError,UnicodeError):err={}
                detail="; provider=Failed to get quotes" if isinstance(err,dict) and err.get("error")=="Failed to get quotes" else ""
                raise SellQuoteRejected(stage+": HTTP 400; no_retry"+detail)
            res.raise_for_status();data=bytearray()
            for chunk in res.iter_bytes(chunk_size=65536):
                if len(data)+len(chunk)>limit:raise PilotError(stage+": response_too_large")
                data.extend(chunk)
        raw=json.loads(data)
    except httpx.HTTPStatusError as e:
        message=stage+": HTTP "+str(e.response.status_code)+"; no_retry"
        if stage=="jupiter.sell" and e.response.status_code==400:
            raise SellQuoteRejected(message) from None
        raise PilotError(message) from None
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
def run(*,transport=None,clock=utc):
    if not configured():raise PilotError("Solana veri adaptörü veya kullanım izni/anahtarı eksik.")
    mint,pool=sol.config()
    if mint==USDC:raise PilotError("USDC baz token olamaz.")
    key=os.getenv("CYBERBOT_JUPITER_KEY","").strip()
    if key and (len(key)>256 or not re.fullmatch(r"[A-Za-z0-9_.-]+",key)):raise PilotError("API anahtarı biçimi geçersiz.")
    rpc_name,rpc_url=rpc_endpoint()
    holder_mode=os.getenv("CYBERBOT_SOLANA_HOLDER_MODE","rpc")
    if holder_mode not in ("rpc","public_reports"):raise PilotError("Invalid holder diagnostic mode")
    started=clock()
    with httpx.Client(timeout=httpx.Timeout(8,connect=6),follow_redirects=False,trust_env=False) as c:
        def get(kind,params):return transport(kind,params) if transport else request(c,kind,params,key,rpc_url=rpc_url)
        info=mint_info(get("rpc",("getAccountInfo",[mint,{"encoding":"jsonParsed","commitment":"finalized"}])))
        if holder_mode=="public_reports":
            holders=reported_holders(get("rugcheck",mint),get("gecko_holders",mint),mint)
        else:
            holders=concentration(get("rpc",("getTokenLargestAccounts",[mint,{"commitment":"finalized"}])),info)
        pooldata=pool_info(get("pool",pool),mint,pool)
        def query(a,b,n):return quote(get("quote",{"inputMint":a,"outputMint":b,"amount":str(n)}),a,b,n,pool)
        tokens=query(USDC,mint,AMOUNT)
        received=query(mint,USDC,tokens)
    elapsed=(clock()-started).total_seconds()
    if not 0<=elapsed<=30:raise PilotError("Tanılama süresi aşıldı.")
    units=D(tokens)/D(10**info["decimals"])
    ask=D(100)/units;bid=(D(received)/D(10**6))/units
    return {"status":"diagnostic_only","mint":mint,"pool":pool,"retrieved_at":clock().isoformat(),"quote_currency":"USDC","test_input_usdc":"100","quoted_tokens":str(units),"quoted_return_usdc":str(D(received)/D(10**6)),"indicative_ask_usdc":str(ask),"indicative_bid_usdc":str(bid),"roundtrip_indicative_pct":str((D(received)/D(AMOUNT)-1)*100),"pool":pooldata,"mint_checks":{**info,**holders},"quote_source_timestamp_verified":False,"usd_conversion_verified":False,"security_verified":False,"depth_verified":False,"pilot_applied":False,"live_data_verified":False,"real_orders":False,"transport_mocked":transport is not None,"api_key_used":bool(key),"rpc_provider":rpc_name,"holder_mode":holder_mode,"blockers":(["Third-party holder reports are not finalized RPC or verified wallet evidence"] if holder_mode=="public_reports" else [])+["USDC/USD dönüşümü yok","Kaynak zaman damgası ve eşzamanlılık doğrulanmadı","Token hesabı yoğunlaşması cüzdan yoğunlaşması değildir","Kotasyon dolum ve derinlik garantisi değildir"]}
