"""Research-only champion/challenger tournament; frozen final holdout, no order access."""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date,datetime,timezone
from decimal import Decimal as D
from pathlib import Path
from .capital import CAPITAL
from .engine import FEE,SLIP
from .learning import WINDOWS
from .robustness import evaluate
from .strategy_lab import simulate

VERSION="tournament-1"
HOLDOUT=60
MIN_SCORE=65
MIN_MARGIN=5
MIN_FINAL_TRADES=5

def tournament(raw,*,mode,market,symbol):
    if market not in CAPITAL or mode not in ("synthetic","historical_unverified"):
        raise ValueError("Geçersiz piyasa veya veri modu.")
    if not 240<=len(raw)<=1000:raise ValueError("Turnuva için 240–1000 gözlem gerekli.")
    bars=[];canonical=[];prev=None
    for row in raw:
        o,c=(D(str(row[k])) for k in ("open","close"))
        if any(not x.is_finite() or not D("1e-12")<=x<=D("1e9") for x in (o,c)):raise ValueError("Geçersiz fiyat.")
        session=row.get("session")
        if mode=="historical_unverified":
            d=date.fromisoformat(session)
            if prev is not None and d<=prev:raise ValueError("Tarih sırası geçersiz.")
            prev=d
        bars.append((o,c));canonical.append([str(o.normalize()),str(c.normalize()),session])
    split=len(bars)-HOLDOUT
    discovery=evaluate(raw[:split],mode=mode,market=market,symbol=symbol)
    ranking=sorted(discovery["strategies"],key=lambda s:(s["status"]!="research_candidate",-(s["score"] if s["score"] is not None else -1),s["id"]))
    eligible=[s for s in ranking if s["status"]=="research_candidate" and s["score"] is not None and s["score"]>=MIN_SCORE]
    candidate=eligible[0] if eligible else None
    margin=None if len(eligible)<2 else round(candidate["score"]-eligible[1]["score"],2)
    fingerprint=hashlib.sha256(json.dumps([VERSION,mode,market,symbol,str(FEE),str(SLIP),canonical],separators=(",",":")).encode()).hexdigest()
    currency,capital=CAPITAL[market]
    result={"id":fingerprint,"version":VERSION,"mode":mode,"market":market,"symbol":symbol,"currency":currency,"initial_capital":str(capital),
            "scope":"single_symbol","observations":len(bars),"discovery_observations":split,"final_holdout_observations":HOLDOUT,
            "final_start_session":canonical[split][2],"final_end_session":canonical[-1][2],
            "ranking":[{k:s[k] for k in ("id","name","score","status","oos_return_pct","oos_drawdown_pct","closed_trades")} for s in ranking],
            "candidate":candidate["id"] if candidate else None,"challengers":[s["id"] for s in eligible[1:]],"score_margin":margin,
            "research_champion":None,"status":"no_eligible_candidate","validation":None,
            "market_wide_champion":None,"promotion_enabled":False,"real_orders":False,"profitability_verified":False,
            "limits":["Tek sembol araştırması; piyasanın tamamı için şampiyon seçilmez.",
                      "Son 60 gözlem aday seçimine veya pencere seçimine katılmaz. Sadece önceden seçilen aday sınanır.",
                      "Aynı veya örtüşen veri tekrar kullanılırsa bağımsız kanıt sayılmaz. Sentetik şampiyon gerçek piyasa kanıtı değildir.",
                      "Sabit araştırma eşikleri deneysel; gerçek emir, paper emir veya otomatik terfi yok."]}
    if candidate is None:return result
    if margin is not None and margin<MIN_MARGIN:
        result["status"]="close_candidates"
        return result
    name=candidate["id"]
    # Freeze parameter using only discovery; final holdout is not used to choose a runner-up.
    window=max(WINDOWS,key=lambda w:simulate(bars,name,w,20,split)["return"])
    def summary(s):
        return {"return_pct":round(float(s["return"])*100,4),"drawdown_pct":round(float(s["drawdown"])*100,4),
                "closed_trades":s["closed"],"ending_capital":str((capital*(1+s["return"])).quantize(D(".01")))}
    base=simulate(bars,name,window,split,len(bars))
    costly=simulate(bars,name,window,split,len(bars),fee=FEE*2,slip=SLIP*2)
    benchmark=simulate(bars,"buy_hold",3,split,len(bars))
    checks={"positive_return":base["return"]>0,"positive_double_cost":costly["return"]>0,
            "drawdown_within_limit":base["drawdown"]<=D(".10"),"stress_drawdown_within_limit":costly["drawdown"]<=D(".10"),
            "enough_final_trades":base["closed"]>=MIN_FINAL_TRADES}
    result["validation"]={"window":window,"base":summary(base),"double_cost":summary(costly),"buy_hold_reference":summary(benchmark),"checks":checks}
    result["status"]="validated_research_candidate" if all(checks.values()) else "final_validation_failed"
    if all(checks.values()):result["research_champion"]=name
    return result

class TournamentJournal:
    def __init__(self,path):
        self.path=Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path,timeout=5)) as db,db:
            db.execute("CREATE TABLE IF NOT EXISTS tournaments(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,mode TEXT NOT NULL,market TEXT NOT NULL,symbol TEXT NOT NULL,payload TEXT NOT NULL)")
    def save(self,result):
        with closing(sqlite3.connect(self.path,timeout=5)) as db,db:
            return bool(db.execute("INSERT OR IGNORE INTO tournaments VALUES(?,?,?,?,?,?)",(result["id"],datetime.now(timezone.utc).isoformat(),result["mode"],result["market"],result["symbol"],json.dumps(result,ensure_ascii=False))).rowcount)
    def recent(self,market,mode):
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            rows=db.execute("SELECT created_at,payload FROM tournaments WHERE market=? AND mode=? ORDER BY created_at DESC LIMIT 20",(market,mode)).fetchall()
        return [{"created_at":stamp,"id":d["id"],"symbol":d["symbol"],"status":d["status"],"candidate":d["candidate"],"research_champion":d["research_champion"],"final_start_session":d["final_start_session"],"final_end_session":d["final_end_session"]} for stamp,payload in rows for d in [json.loads(payload)]]
    def get(self,key):
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            row=db.execute("SELECT payload FROM tournaments WHERE id=?",(key,)).fetchone()
        return json.loads(row[0]) if row else None
