"""Opt-in read-only conditional strategy report; never invokes a trade action."""
import json
from contextlib import closing
from datetime import datetime,timezone
from cyberbot import observed_pilot, pilot_decisions
from cyberbot.conditional_strategy_review import snapshot, VERSION
from .adaptive_review import readonly


def run():
    out={"version":VERSION,"markets":{},"automatic_strategy_switching":False,
         "real_orders":False}
    if not pilot_decisions.enabled():
        return {**out,"status":"DISABLED"}
    path=observed_pilot.path()
    if not path.is_file():
        return {**out,"status":"NO_OBSERVATIONS"}
    now=datetime.now(timezone.utc)
    with closing(readonly(path)) as db:
        db.execute("BEGIN")
        for market in pilot_decisions.MARKETS:
            if not pilot_decisions.market_enabled(market):
                out["markets"][market]={"status":"DISABLED","action":"HOLD"}
                continue
            out["markets"][market]=snapshot(db,market,now)
    return {**out,"status":"RESEARCH_ONLY"}


if __name__=="__main__":
    print(json.dumps(run(),indent=2,allow_nan=False))
