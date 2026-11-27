"""Read-only Solana research page served through the existing app access guard."""
import os
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse,JSONResponse
from tools.solana_pwa_publish import read,unavailable

router=APIRouter()

@router.get("/api/solana/research-status")
def research_status():
    try:data=read(os.getenv("CYBERBOT_SOLANA_PWA_REPORT_DIR"))
    except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError,OSError):
        data=unavailable("error")
    return JSONResponse(data,headers={"Cache-Control":"no-store"})

@router.get("/solana/research",response_class=HTMLResponse)
def research_page():
    return (Path(__file__).parent/"web"/"solana-research.html").read_text(encoding="utf-8")
