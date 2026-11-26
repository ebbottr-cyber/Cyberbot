"""Read-only dashboard of persisted research, not a live trading or training process."""
import json
import sqlite3
from contextlib import closing
from .capital import CAPITAL
from .futures import START
from .research_pipeline import research_path
from .strategy_memory import VERSION as MEMORY_VERSION

MARKETS={**{k:(v[0],str(v[1])) for k,v in CAPITAL.items()},"FUTURES":("USDT",str(START))}
MODES=("synthetic","historical_unverified")

def overview(mode):
    if mode not in MODES:raise ValueError("Geçersiz veri modu.")
    result={"mode":mode,"status":"empty","markets":[{"market":m,"currency":c,"initial_capital":v,"experiments":0,"latest":[]} for m,(c,v) in MARKETS.items()],
            "recent":[],"total_experiments":0,"real_orders":False,"promotion_enabled":False,"profitability_verified":False,
            "limitations":["Kayıt sayısı bağımsız kanıt veya öğrenme başarısı değildir.",
                           "Sonuçlar tek sembol ve deney kapsamındadır. Piyasalar arasında puan sıralaması yapılmaz.",
                           "Gölge bakiyeleri ana sanal kasadan ayrıdır; birleştirilmez.",
                           "Tahmin hataları geçmiş deneylere aittir; canlı Chronos 2 ve LLM doğrulaması bu kayıtlardan çıkarılamaz."]}
    path=research_path()
    if not path.is_file():return result
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "research_pipeline" not in tables:return result
        for m in result["markets"]:
            market=m["market"]
            m["experiments"]=db.execute("SELECT count(*) FROM research_pipeline WHERE mode=? AND market=?",(mode,market)).fetchone()[0]
            result["total_experiments"]+=m["experiments"]
            # Latest experiment for each symbol; at most ten symbols per market.
            records=db.execute("""SELECT id,created_at,symbol,payload FROM (
                SELECT id,created_at,symbol,payload,ROW_NUMBER() OVER(PARTITION BY symbol ORDER BY created_at DESC,id DESC) AS rn
                FROM research_pipeline WHERE mode=? AND market=?
                ) WHERE rn=1 ORDER BY created_at DESC,id DESC LIMIT 10""",(mode,market)).fetchall()
            for key,created,symbol,payload in records:
                d=json.loads(payload)
                if (d.get("market"),d.get("mode"),d.get("symbol"),d.get("id"))!=(market,mode,symbol,key):raise ValueError("Araştırma kaydı uyumsuz.")
                s=d.get("summary",{});a=d.get("adaptive",{})
                ranking=d.get("ranking") if market=="FUTURES" else d.get("robustness",{}).get("strategies")
                strategies=[]
                for row in ranking or []:
                    strategies.append({"id":row["id"],"name":row["name"],"score":row.get("score"),"status":row.get("status"),
                                       "return_pct":row.get("return_pct",row.get("oos_return_pct")),
                                       "drawdown_pct":row.get("drawdown_pct",row.get("oos_drawdown_pct")),
                                       "loss_path_pct":row.get("monte_carlo",{}).get("loss_path_pct")})
                states={}
                if "strategy_memory" in tables:
                    scope=json.dumps([MEMORY_VERSION,mode,market,symbol],ensure_ascii=False,separators=(",",":"))
                    for strategy,p in db.execute("SELECT strategy,payload FROM strategy_memory WHERE scope=?",(scope,)):
                        states[strategy]=json.loads(p)
                candidate=s.get("next_candidate")
                if states.get(candidate,{}).get("status")=="quarantined":candidate="cash"
                m["latest"].append({"id":key,"created_at":created,"symbol":symbol,"version":d.get("version"),
                    "regime":s.get("regime"),"research_champion":s.get("research_champion"),"candidate_at_experiment":s.get("next_candidate"),
                    "candidate_after_quarantine":candidate,"shadow":a.get("shadow"),"double_cost_shadow":a.get("double_cost_shadow"),
                    "strategies":strategies,"memory":states,"models":d.get("models",{}).get("models",[]),
                    "chronos_runtime_verified":False,"llm_runtime_verified":False})
        result["recent"]=[dict(zip(("id","created_at","market","symbol"),row)) for row in db.execute("SELECT id,created_at,market,symbol FROM research_pipeline WHERE mode=? ORDER BY created_at DESC,id DESC LIMIT 30",(mode,))]
    result["status"]="recorded" if result["total_experiments"] else "empty"
    return result
