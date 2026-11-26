"""Persistent entry-only emergency brake, serialized with pilot ledger writes."""
import os,json,sqlite3
from contextlib import closing

def halted(db):
    if os.getenv("CYBERBOT_PILOT_KILL_SWITCH")=="1":return True
    row=db.execute("SELECT payload FROM observed_events WHERE market='CONTROL' AND event='entry_control' ORDER BY id DESC LIMIT 1").fetchone()
    if not row:return False
    value=json.loads(row[0]).get("halted")
    if type(value) is not bool:raise ValueError("Geçersiz giriş kontrolü.")
    return value
def change(stop,*,clock=None):
    from . import observed_pilot as p
    if type(stop) is not bool:raise p.PilotError("Geçersiz kontrol.")
    if not stop and os.getenv("CYBERBOT_PILOT_KILL_SWITCH")=="1":raise p.PilotError("Ortam acil durdurması açık.")
    with p.tx() as db:
        now=(clock or p.utc)().isoformat();cancelled=[]
        if stop:
            for m,payload in db.execute("SELECT market,payload FROM observed_accounts").fetchall():
                s=json.loads(payload);pending=s.get("pending")
                if pending and pending.get("side") in ("buy","LONG","SHORT"):
                    s["pending"]=None
                    db.execute("UPDATE observed_accounts SET payload=? WHERE market=?",(json.dumps(s,allow_nan=False),m))
                    db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES(?,?,?,?)",(m,now,"entry_cancelled",json.dumps({"reason":"kill_switch","cancelled":pending})))
                    cancelled.append(m)
        result={"halted":stop,"cancelled_markets":cancelled,"at":now,"automatic_entry_enabled":False,"real_orders":False}
        db.execute("INSERT INTO observed_events(market,at,event,payload) VALUES('CONTROL',?,'entry_control',?)",(now,json.dumps(result)))
        return result
def snapshot():
    from . import observed_pilot as p
    path=p.path();result={"halted":os.getenv("CYBERBOT_PILOT_KILL_SWITCH")=="1","automatic_entry_enabled":False,"real_orders":False}
    if path.is_file():
        with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='observed_events'").fetchone():result["halted"]=halted(db)
    return result
