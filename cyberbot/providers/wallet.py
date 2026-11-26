"""Public Solana signature observations; no wallet keys, signing or order methods."""
import json
import time
from threading import Lock
from urllib.request import Request, urlopen
from urllib.error import URLError
from .solana_meme import is_solana_address

RPC="https://api.mainnet-beta.solana.com"
class WalletError(ValueError): pass

def rpc_read(address,limit):
    payload={"jsonrpc":"2.0","id":1,"method":"getSignaturesForAddress","params":[address,{"limit":limit,"commitment":"finalized"}]}
    req=Request(RPC,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
    try:
        with urlopen(req,timeout=8) as response:
            raw=response.read(500001)
        if len(raw)>500000: raise WalletError("Yanıt boyutu sınırı aşıldı.")
        data=json.loads(raw)
        if not isinstance(data,dict) or data.get("id")!=1 or "error" in data or not isinstance(data.get("result"),list):
            raise WalletError("RPC verisi alınamadı.")
        return data["result"]
    except (URLError,OSError,ValueError) as e:
        raise WalletError("Solana RPC yanıt vermedi veya kota doldu.") from None

class WalletFeed:
    def __init__(self,transport=rpc_read,clock=time.monotonic):
        self.transport=transport
        self.clock=clock
        self.lock=Lock()
        self.cache={}
        self.last_attempt=None

    def observe(self,address,limit=20):
        if not is_solana_address(address) or type(limit) is not int or not 1<=limit<=50:
            raise WalletError("Geçersiz açık cüzdan adresi veya kayıt sınırı.")
        key=(address,limit)
        with self.lock:
            now=self.clock()
            if key in self.cache and now-self.cache[key][0]<60:
                return {**self.cache[key][1],"cached":True}
            if self.last_attempt is not None and now-self.last_attempt<5:
                raise WalletError("RPC kota koruması: 5 saniye bekleyin.")
            self.last_attempt=now
            raw=self.transport(address,limit)
            if not isinstance(raw,list) or len(raw)>limit:
                raise WalletError("RPC veri biçimi geçersiz.")
            rows=[]
            for row in raw:
                if not isinstance(row,dict) or not isinstance(row.get("signature"),str) or not 64<=len(row["signature"])<=100 or type(row.get("slot")) is not int or row["slot"]<0 or "err" not in row:
                    raise WalletError("İşlem gözlemi geçersiz.")
                ts=row.get("blockTime")
                if ts is not None and (type(ts) is not int or ts<0): raise WalletError("Zaman damgası geçersiz.")
                rows.append({"signature":row["signature"],"slot":row["slot"],"block_time":ts,"success":row["err"] is None})
            result={"address":address,"source":"solana_public_rpc","observations":rows,"cached":False,"swap_verified":False,"profitability_verified":False,"real_orders":False}
            if len(self.cache)>=128: self.cache.pop(next(iter(self.cache)))
            self.cache[key]=(self.clock(),result)
            return result
