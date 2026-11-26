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
