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
def news_panel():
    import os
    html = (ROOT/"news.html").read_text(encoding="utf-8")
    if os.getenv("CYBERBOT_NOTIFICATION_PANEL_ENABLED") == "1":
        html = html.replace("</body>", '<main id="structuredResearchNews" aria-label="Yapılandırılmış araştırma haberleri"></main><script type="module" src="/ui/notifications/news-host.js"></script></body>', 1)
    return html
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

from .news_graph import graph,asset_link
@router.get("/api/news/graph")
def news_graph(market:str="ALL"):
    try:return graph(market)
    except ValueError as e:raise HTTPException(422,str(e)) from None
    except (OSError,sqlite3.Error):raise HTTPException(503,"Haber ağı okunamadı.") from None
class AssetLink(BaseModel):
    record_key:str=Field(max_length=80)
    market:str=Field(max_length=16)
    symbol:str=Field(max_length=44)
    evidence_url:str=Field(max_length=2048)
@router.post("/api/news/graph/link")
def link_asset(body:AssetLink):
    try:return asset_link(**body.model_dump())
    except ValueError as e:raise HTTPException(422,str(e)) from None
    except (OSError,sqlite3.Error):raise HTTPException(503,"Bağlantı kaydedilemedi.") from None

from .news_impact import demo as impact_demo,recent as impact_recent
@router.get("/api/news/impact")
def impact():
    try:return {"demo":impact_demo(),"records":impact_recent(),"real_orders":False}
    except (OSError,sqlite3.Error,ValueError):raise HTTPException(503,"Olay araştırması okunamadı.") from None

from .news_memory import overview as news_memory
@router.get("/api/news/memory")
def memory(market:str="ALL"):
    try:return news_memory(market)
    except ValueError as e:raise HTTPException(422,str(e)) from None
    except (OSError,sqlite3.Error,KeyError,TypeError,ArithmeticError):raise HTTPException(503,"Haber performans hafızası okunamadı.") from None

from .news_agents import review as agent_review,local_checklist,AgentError
from .models_api import _lock as model_lock
import os
@router.get("/api/news/agents/{record_key}")
def agents(record_key:str):
    try:return agent_review(record_key)
    except AgentError as e:raise HTTPException(422,str(e)) from None
    except (OSError,sqlite3.Error,ValueError,KeyError,TypeError,ArithmeticError):raise HTTPException(503,"Haber ajanları çalıştırılamadı.") from None
@router.post("/api/news/agents/{record_key}/checklist")
def agents_model(record_key:str):
    model=os.getenv("CYBERBOT_OLLAMA_MODEL")
    if os.getenv("CYBERBOT_LOCAL_LLM_ENABLED")!="1" or os.getenv("CYBERBOT_NEWS_LLM_ENABLED")!="1" or not model:raise HTTPException(403,"Yerel haber modeli kapalı.")
    if not model_lock.acquire(blocking=False):raise HTTPException(429,"Model meşgul.")
    try:return local_checklist(agent_review(record_key),model)
    except AgentError as e:raise HTTPException(422,str(e)) from None
    except (OSError,sqlite3.Error,ValueError,KeyError,TypeError,ArithmeticError):raise HTTPException(503,"Haber modeli kullanılamadı.") from None
    finally:model_lock.release()

from .news_overview import snapshot as news_snapshot
@router.get("/api/news/overview")
def overview_news():
    try:return news_snapshot()
    except (OSError,sqlite3.Error,ValueError,KeyError,TypeError,ArithmeticError):raise HTTPException(503,"Haber özeti okunamadı.") from None

@router.get("/ui/panel-mobile.css")
def mobile_style():return Response((ROOT/"panel-mobile.css").read_text(encoding="utf-8"),media_type="text/css")
