"""Current panel alerts from local records only; no notifications, writes or orders."""
from contextlib import closing
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import os
import sqlite3
from .operations import health
from .worker import status as worker_status
from .capital import fx_quote
from .db_paths import checked
from .providers.intraday_coverage import coverage_5m

MARKETS={"BIST":"paper_bist","NASDAQ":"paper_nasdaq","XETRA":"paper_xetra","SOLANA":"paper_solana","FUTURES":"futures"}

def recorded_risks(paths):
    result={}
    for m,role in MARKETS.items():
        path=paths[role]
        if not path.is_file():continue
        table="futures_equity_history" if m=="FUTURES" else "equity_history"
        try:
            with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=2)) as db:
                row=db.execute(f"SELECT at,drawdown FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                dd=Decimal(row[1])
                if dd.is_finite() and dd>=0:result[m]={"at":row[0],"drawdown":dd}
        except (sqlite3.Error,OSError,ValueError,TypeError,InvalidOperation):continue
    return result

def compose(h,w,fx,cov,risks,now=None):
    items=[]
    def add(key,severity,category,title,message,link):
        items.append(dict(id=key,severity=severity,category=category,title=title,message=message,link=link))
    for name,value in h["databases"].items():
        if value=="not_initialized":
            add("db-"+name,"info","system","Veritabanı henüz başlatılmadı",name+" · İlk kurulum gerekebilir.","/health")
        elif value!="ok":
            add("db-"+name,"critical","system","Veritabanı kontrolü başarısız",name+" · "+value,"/health")
    last=w.get("last_cycle") or {}
    if w["status"]=="unavailable":
        add("worker","warning","learning","Araştırma kayıtları okunamadı","Görev kaydına erişilemiyor.","/development")
    elif w["status"]=="not_started":
        add("worker","info","learning","Araştırma görevi kaydı yok","Canlı çalışma durumu doğrulanmadı.","/development")
    elif last.get("status") not in ("ok",None):
        add("worker","warning","learning","Son araştırma döngüsü sorunlu","Son kayıt: "+str(last.get("status")),"/development")
    if fx.get("status")!="fresh_input" or fx.get("usdtusd_status")!="fresh_input":
        add("fx","warning","data","Birleşik portföy için kur eksik veya eski","USD/TRY ve USDT/USD girdileri güncel değilse toplam hesaplanmaz.","/data")
    for m,v in cov["markets"].items():
        if v["status"]=="unavailable":
            add("coverage-"+m,"info","data",m+" arşiv raporu bağlı değil","İndirme durumu bilinmiyor; sıfır veri anlamına gelmez.","/data")
        elif v["downloaded"]<v["target"]:
            add("coverage-"+m,"warning","data",m+" arşiv kapsamı eksik",str(v["target"]-v["downloaded"])+" sembol yerel raporda eksik.","/data")
    for m,r in risks.items():
        dd=r["drawdown"]
        if dd>=10:
            add("risk-"+m,"warning","risk",m+" kayıtlı düşüş eşiği aşıldı","Son kayıt: %"+str(dd.quantize(Decimal("0.01")))+" · "+str(r["at"])+" · Sentetik; güncel fiyat değildir.","/#portfolio")
        elif dd>=7:
            add("risk-"+m,"info","risk",m+" kayıtlı düşüş izleme eşiğinde","Son kayıt: %"+str(dd.quantize(Decimal("0.01")))+" · "+str(r["at"])+" · Sentetik; güncel fiyat değildir.","/#portfolio")
    if not h.get("model_runtime_verified"):
        add("models","info","learning","Canlı model doğrulaması yok","Chronos 2 ve LLM gerçek çalışma başarısı henüz doğrulanmadı.","/models")
    order={"critical":0,"warning":1,"info":2}
    items.sort(key=lambda x:(order[x["severity"]],x["id"]))
    return {"as_of":(now or datetime.now(timezone.utc)).isoformat(),"items":items,
        "counts":{s:sum(x["severity"]==s for x in items) for s in order},
        "risk_scope":"latest_recorded_synthetic_drawdown","push_enabled":False,"live_monitoring":False,"real_orders":False}

def snapshot():
    h=health();w=worker_status()
    cov=coverage_5m(os.getenv("CYBERBOT_NASDAQ_5M_REPORT"),os.getenv("CYBERBOT_BIST_XETRA_5M_REPORT"))
    risks={} if h.get("databases",{}).get("path_isolation")=="collision" else recorded_risks(checked())
    return compose(h,w,fx_quote(),cov,risks)
