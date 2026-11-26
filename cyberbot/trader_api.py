import os
import json
from pathlib import Path
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import HTMLResponse
from .providers.wallet import WalletFeed,WalletError
from .trader import evaluate,demo,ResearchError

router=APIRouter()
feed=WalletFeed()

@router.get("/traders",response_class=HTMLResponse)
def panel():
    return (Path(__file__).parent/"web"/"traders.html").read_text(encoding="utf-8")

@router.post("/api/traders/wallet")
def wallet(address:str,limit:int=Query(20,ge=1,le=50)):
    if os.getenv("CYBERBOT_SOLANA_READ_ENABLED")!="1":
        raise HTTPException(403,"Salt okunur Solana erişimi kapalı.")
    try: return feed.observe(address,limit)
    except WalletError as e: raise HTTPException(422,str(e)) from None

@router.get("/api/traders/research")
def research():
    path=os.getenv("CYBERBOT_SHADOW_FILE")
    if not path: return {"mode":"synthetic","traders":demo(),"profitability_verified":False}
    try:
        p=Path(path)
        if not p.is_file() or p.stat().st_size>2000000: raise ResearchError("Gölge dosyası bulunamadı veya çok büyük.")
        with p.open("rb") as f: data=f.read(2000001)
        if len(data)>2000000: raise ResearchError("Gölge dosyası çok büyük.")
        return {"mode":"manual_unverified","traders":evaluate(json.loads(data)),"profitability_verified":False}
    except (OSError,ValueError,ResearchError):
        raise HTTPException(422,"Gölge kanıtı okunamadı veya geçersiz.") from None
