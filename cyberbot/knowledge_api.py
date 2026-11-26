from pathlib import Path
import sqlite3
from fastapi import APIRouter,HTTPException
from fastapi.responses import HTMLResponse,Response
from pydantic import BaseModel,Field
from .knowledge import snapshot,vault_zip
from .news import list_refs,save
router=APIRouter()
ROOT=Path(__file__).parent/"web"
@router.get("/knowledge",response_class=HTMLResponse)
def panel():return (ROOT/"knowledge.html").read_text(encoding="utf-8")
@router.get("/news",response_class=HTMLResponse)
def news_panel():return (ROOT/"news.html").read_text(encoding="utf-8")
@router.get("/ui/obsidian.css")
def style():return Response((ROOT/"obsidian.css").read_text(encoding="utf-8"),media_type="text/css")
@router.get("/api/knowledge")
def knowledge(mode:str="synthetic"):
    try:return snapshot(mode)
    except ValueError as e:raise HTTPException(422,str(e)) from None
    except (OSError,sqlite3.Error):raise HTTPException(503,"Hafıza okunamadı.") from None
@router.get("/api/knowledge/vault.zip")
def export(mode:str="synthetic"):
    try:return Response(vault_zip(mode),media_type="application/zip",headers={"Content-Disposition":"attachment; filename=Cyberbot-Vault.zip"})
    except ValueError as e:raise HTTPException(422,str(e)) from None
    except (OSError,sqlite3.Error):raise HTTPException(503,"Hafıza okunamadı.") from None
@router.get("/api/news")
def news(market:str="ALL"):
    try:return list_refs(market)
    except ValueError as e:raise HTTPException(422,str(e)) from None
    except (OSError,sqlite3.Error):raise HTTPException(503,"Haber kayıtları okunamadı.") from None
class NewsRef(BaseModel):
    market:str=Field(max_length=16)
    kind:str=Field(max_length=24)
    event_type:str=Field(max_length=16)
    url:str=Field(max_length=2048)
    event_at:str=Field(max_length=64)
    label:str=Field(max_length=160)
    note:str=Field(default="",max_length=500)
@router.post("/api/news")
def add(body:NewsRef):
    try:return save(body.model_dump())
    except ValueError as e:raise HTTPException(422,str(e)) from None
    except (OSError,sqlite3.Error):raise HTTPException(503,"Haber kaydedilemedi.") from None

from .news_feed import read as rss_read,refresh as rss_refresh,analysis as news_analysis,FeedError
@router.get("/api/news/rss")
def rss(market:str="ALL"):
    if market not in ("ALL","BIST","NASDAQ","XETRA","FUTURES","SOLANA","GLOBAL"):raise HTTPException(422,"Geçersiz piyasa.")
    try:return rss_read(market)
    except (ValueError,OSError,sqlite3.Error):raise HTTPException(503,"RSS kayıtları okunamadı.") from None
@router.post("/api/news/rss/{source}")
def update_rss(source:str):
    try:return rss_refresh(source)
    except FeedError as e:raise HTTPException(409,str(e)) from None
    except (ValueError,OSError,sqlite3.Error):raise HTTPException(503,"RSS güncellenemedi.") from None
@router.get("/api/news/analysis")
def analyze_news(market:str="ALL"):
    if market not in ("ALL","BIST","NASDAQ","XETRA","FUTURES","SOLANA","GLOBAL"):raise HTTPException(422,"Geçersiz piyasa.")
    try:return news_analysis(market)
    except (ValueError,OSError,sqlite3.Error):raise HTTPException(503,"Haber analizi okunamadı.") from None
