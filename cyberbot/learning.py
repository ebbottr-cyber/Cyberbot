"""Offline walk-forward research journal. No automatic promotion or trading."""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from decimal import Decimal as D
from pathlib import Path
from .strategy_lab import simulate, STRATEGIES
from .engine import FEE, SLIP

VERSION="walkforward-1"
WINDOWS=(3,5,10,15,20)
TRAIN=60
TEST=20
MIN_FOLDS=3

def demo_rows():
    rows=[]
    prior=D(100)
    for i in range(240):
        shift=(D(".002"),D("-.002"),D(0))[i//80]
        close=prior*(1+shift+D(((i*17)%19)-9)/1000)
        rows.append({"open":str(prior),"close":str(close)})
        prior=close
    return rows

def research(raw,*,mode,symbol):
    if mode not in ("synthetic","historical_unverified"):raise ValueError("Geçersiz veri modu.")
    if not 120<=len(raw)<=6000:raise ValueError("En az 120 gözlem gerekli (en çok 6000).")
    bars=[];dates=[];previous=None
    for row in raw:
        o,c=(D(str(row[k])) for k in ("open","close"))
        if any(not x.is_finite() or not D("0.000000000001")<=x<=D("1000000000") for x in (o,c)):
            raise ValueError("Geçersiz fiyat.")
        session=row.get("session")
        if mode=="historical_unverified":
            day=date.fromisoformat(session)
            if previous is not None and day<=previous:raise ValueError("Tarih sırası geçersiz.")
            previous=day
        bars.append((o,c));dates.append(session)
    # Frozen protocol: training window rolls forward; validation intervals never overlap.
    fingerprint=hashlib.sha256(json.dumps([VERSION,mode,symbol,str(FEE),str(SLIP),[[str(o.normalize()),str(c.normalize()),d] for (o,c),d in zip(bars,dates)]],ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
    def pct(v):return str((v*100).quantize(D(".01")))
    results=[]
    for name,label in STRATEGIES.items():
        folds=[];net=D(1);worst=D(0);wins=0;total=0;positive=0
        for start in range(TRAIN,len(bars)-TEST+1,TEST):
            train_start=start-TRAIN+20
            chosen=max(WINDOWS,key=lambda w:simulate(bars,name,w,train_start,start)["return"]) if name not in ("cash","buy_hold") else 3
            train=simulate(bars,name,chosen,train_start,start)
            hold=simulate(bars,name,chosen,start,start+TEST)
            # Each fold begins flat; compounded fold returns are a research statistic.
            net*=1+hold["return"]
            worst=max(worst,hold["drawdown"])
            wins+=hold["wins"];total+=hold["closed"];positive+=hold["return"]>0
            folds.append({"test_start":start,"test_end_exclusive":start+TEST,"window":chosen,"training_pct":pct(train["return"]),"test_pct":pct(hold["return"]),"drawdown_pct":pct(hold["drawdown"])})
        n=len(folds)
        status="referans" if name in ("cash","buy_hold") else "yetersiz_islem" if total<10 or n<MIN_FOLDS else "inceleme_adayi" if net>1 and positive*2>=n and worst<=D(".10") else "zayif_sonuc"
        results.append({"id":name,"name":label,"folds":folds,"fold_count":n,"positive_folds":positive,"closed":total,"win_pct":pct(D(wins)/total) if total else None,"compounded_pct":pct(net-1),"worst_fold_drawdown_pct":pct(worst),"status":status})
    return {"id":fingerprint,"version":VERSION,"mode":mode,"symbol":symbol,"observations":len(bars),"training_window":TRAIN,"training_scored":40,"test_window":TEST,"fee_bps":str(FEE*10000),"slippage_bps":str(SLIP*10000),"strategies":results,"promotion_enabled":False,"real_orders":False,"limitations":["Her test bölümü nakitle başlar; birleşik getiri gerçek portföy performansı değildir.","En kötü bölüm düşüşü, bütün dönem maksimum düşüşü değildir.","Eşikler deneysel; bağımsız veri, likidite ve kurumsal işlem doğrulanmadı.","Aynı veride farklı deneyler bağımsız kanıt değildir. Hiçbir sonuç otomatik terfi etmez."]}

class Journal:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path,timeout=5)) as c,c:
            c.execute("CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,mode TEXT NOT NULL,symbol TEXT NOT NULL,payload TEXT NOT NULL)")
    def save(self,result):
        with closing(sqlite3.connect(self.path,timeout=5)) as c,c:
            inserted=c.execute("INSERT OR IGNORE INTO experiments VALUES (?,?,?,?,?)",(result["id"],datetime.now(timezone.utc).isoformat(),result["mode"],result["symbol"],json.dumps(result,ensure_ascii=False))).rowcount
        return bool(inserted)
    def recent(self):
        with closing(sqlite3.connect(self.path,timeout=5)) as c:
            counts=dict(c.execute("SELECT mode,count(*) FROM experiments GROUP BY mode"))
            rows=c.execute("SELECT id,created_at,mode,symbol FROM experiments ORDER BY created_at DESC LIMIT 50").fetchall()
        return {"counts":counts,"recent":[dict(zip(("id","created_at","mode","symbol"),row)) for row in rows],"promotion_enabled":False}
    def get(self,key):
        with closing(sqlite3.connect(self.path,timeout=5)) as c:
            row=c.execute("SELECT payload FROM experiments WHERE id=?",(key,)).fetchone()
        return json.loads(row[0]) if row else None
