"""Persistent synthetic paper ledger. No broker, wallet, or external calls."""
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone
from pathlib import Path
from .market import INDEX, quote

D = Decimal
START = D("10000")
FEE = D("0.001")
SLIP = D("0.002")
RISK = D("0.01")
MAX_DRAWDOWN = D("0.10")
DAILY_LOSS = D("0.03")
MAX_OPEN = 5
MAX_NOTIONAL = D("0.20")
STOP = D("0.05")
TARGET = D("0.10")

def day():
    return datetime.now(timezone.utc).date().isoformat()

class PaperError(ValueError):
    pass

class Ledger:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.tx() as c:
            c.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), cash TEXT NOT NULL, tick INTEGER NOT NULL, peak TEXT NOT NULL, day TEXT NOT NULL, day_equity TEXT NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, quantity TEXT NOT NULL, entry TEXT NOT NULL, cost TEXT NOT NULL, stop TEXT NOT NULL, target TEXT NOT NULL, opened_tick INTEGER NOT NULL, exit TEXT, pnl TEXT, closed_tick INTEGER, reason TEXT)")
            c.execute("INSERT OR IGNORE INTO state VALUES (1, ?, 0, ?, ?, ?)", (str(START),str(START),day(),str(START)))

            c.execute("CREATE TABLE IF NOT EXISTS equity_history (id INTEGER PRIMARY KEY, at TEXT NOT NULL, tick INTEGER NOT NULL, equity TEXT NOT NULL, drawdown TEXT NOT NULL)")
            if not c.execute("SELECT 1 FROM equity_history LIMIT 1").fetchone():
                self._record(c)

    def _record(self,c):
        s,equity=self._refresh(c)
        dd=(1-equity/D(s["peak"]))*100
        c.execute("INSERT INTO equity_history(at,tick,equity,drawdown) VALUES (?,?,?,?)",(datetime.now(timezone.utc).isoformat(),s["tick"],str(equity),str(dd)))

    @contextmanager
    def tx(self):
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def _state(self,c):
        return c.execute("SELECT * FROM state WHERE id=1").fetchone()

    def _open(self,c):
        return c.execute("SELECT * FROM trades WHERE exit IS NULL ORDER BY id").fetchall()

    def _equity(self,c):
        s=self._state(c)
        return D(s["cash"])+sum((D(t["quantity"])*quote(t["symbol"],s["tick"])*(1-SLIP)*(1-FEE) for t in self._open(c)),D(0))

    def _refresh(self,c):
        s=self._state(c)
        equity=self._equity(c)
        if s["day"] != day():
            c.execute("UPDATE state SET day=?,day_equity=? WHERE id=1",(day(),str(equity)))
        if equity>D(s["peak"]):
            c.execute("UPDATE state SET peak=? WHERE id=1",(str(equity),))
        return self._state(c),equity

    def buy(self,symbol):
        if symbol not in INDEX:
            raise PaperError("Bilinmeyen sembol.")
        with self.tx() as c:
            s,equity=self._refresh(c)
            if equity<=0 or equity<=D(s["peak"])*(1-MAX_DRAWDOWN) or equity<=D(s["day_equity"])*(1-DAILY_LOSS):
                raise PaperError("Risk sınırı: yeni işlem engellendi.")
            opened=self._open(c)
            if len(opened)>=MAX_OPEN or any(t["symbol"]==symbol for t in opened):
                raise PaperError("Açık pozisyon sınırı.")
            price=quote(symbol,s["tick"])*(1+SLIP)
            stop=price*(1-STOP)
            loss_unit=price*(1+FEE)-stop*(1-SLIP)*(1-FEE)
            qty=min(equity*RISK/loss_unit,equity*MAX_NOTIONAL/price,D(s["cash"])/(price*(1+FEE))).quantize(D("0.000001"),rounding=ROUND_DOWN)
            if qty<=0:
                raise PaperError("Yetersiz sanal bakiye.")
            cost=qty*price*(1+FEE)
            c.execute("INSERT INTO trades(symbol,quantity,entry,cost,stop,target,opened_tick) VALUES(?,?,?,?,?,?,?)",(symbol,str(qty),str(price),str(cost),str(stop),str(price*(1+TARGET)),s["tick"]))
            c.execute("UPDATE state SET cash=? WHERE id=1",(str(D(s["cash"])-cost),))
            self._record(c)

    def _sell(self,c,t,reason):
        s=self._state(c)
        price=quote(t["symbol"],s["tick"])*(1-SLIP)
        proceeds=D(t["quantity"])*price*(1-FEE)
        c.execute("UPDATE trades SET exit=?,pnl=?,closed_tick=?,reason=? WHERE id=?",(str(price),str(proceeds-D(t["cost"])),s["tick"],reason,t["id"]))
        c.execute("UPDATE state SET cash=? WHERE id=1",(str(D(s["cash"])+proceeds),))

    def sell(self,trade_id):
        with self.tx() as c:
            t=c.execute("SELECT * FROM trades WHERE id=? AND exit IS NULL",(trade_id,)).fetchone()
            if t is None:
                raise PaperError("Açık işlem bulunamadı.")
            self._sell(c,t,"manuel")
            self._record(c)

    def advance(self):
        with self.tx() as c:
            s=self._state(c)
            if s["tick"]>=min(len(i.prices) for i in INDEX.values())-1:
                raise PaperError("Sentetik veri sonuna ulaşıldı.")
            c.execute("UPDATE state SET tick=tick+1 WHERE id=1")
            tick=s["tick"]+1
            for t in self._open(c):
                p=quote(t["symbol"],tick)
                if p<=D(t["stop"]):
                    self._sell(c,t,"stop")
                elif p>=D(t["target"]):
                    self._sell(c,t,"hedef")
            self._record(c)

    def snapshot(self):
        with self.tx() as c:
            s,equity=self._refresh(c)
            peak=D(s["peak"])
            trades=[dict(t) for t in c.execute("SELECT * FROM trades ORDER BY id DESC")]
            points=c.execute("SELECT at,tick,equity,drawdown FROM equity_history ORDER BY id DESC LIMIT 200").fetchall()
            max_dd=max((D(row[0]) for row in c.execute("SELECT drawdown FROM equity_history")),default=D(0))
            open_markets=len({INDEX[t["symbol"]].market for t in self._open(c)})
            return {"daily_pnl":str((equity-D(s["day_equity"])).quantize(D(".01"))),"return_pct":str(((equity/START-1)*100).quantize(D(".01"))),"open_markets":open_markets,"max_recorded_drawdown_pct":str(max_dd.quantize(D(".01"))),"equity_history":[{"at":p["at"],"tick":p["tick"],"equity":str(D(p["equity"]).quantize(D(".01")))} for p in reversed(points)],"history_limit":200,"mode":"synthetic_paper","real_orders":False,"currency":"USD","cash":str(D(s["cash"]).quantize(D("0.01"))),"equity":str(equity.quantize(D("0.01"))),"pnl":str((equity-START).quantize(D("0.01"))),"drawdown_pct":str(((1-equity/peak)*100).quantize(D("0.01"))),"tick":s["tick"],"open_count":len(self._open(c)),"trades":trades,"markets":[{"market":i.market,"symbol":i.symbol,"price":str(quote(i.symbol,s["tick"]))} for i in INDEX.values()]}
