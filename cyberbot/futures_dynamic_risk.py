"""Read-only Futures dynamic risk proposal; never creates or changes a position."""
import argparse,json,os,sqlite3
from contextlib import closing
from decimal import Decimal as D,ROUND_DOWN
from . import futures_pilot as fut,observed_pilot as stocks
from .futures import FEE,SLIP,LEVERAGE,MMR
from .pilot_control import halted
from .providers import futures_consensus as consensus
from .observed_pilot import PilotError

VERSION="futures-dynamic-risk-1"
def amount(value,lo="0",hi="1000000000000"):
    return fut.number(value,lo,hi)
def evaluate(state,report,now,*,entry_halted):
    out={"version":VERSION,"status":"HOLD","symbol":state.get("symbol"),"evaluated_at":now.isoformat(),
         "blockers":[],"proposal":None,"thresholds_validated":False,"actual_action":"HOLD",
         "paper_orders":False,"pilot_applied":False,"real_orders":False}
    def hold(reason):out["blockers"].append(reason);return out
    sym=state.get("symbol")
    if sym not in ("BTCUSDT","ETHUSDT") or state.get("version")!=fut.VERSION:
        raise PilotError("Risk hesabı kimliği geçersiz.")
    if (not isinstance(report,dict) or report.get("version")!=consensus.VERSION or
        report.get("symbol")!=sym or report.get("status")!="research_only" or
        report.get("actual_action")!="HOLD" or any(report.get(k) is not False for k in
        ("real_orders","paper_orders","pilot_applied"))):
        raise PilotError("Risk araştırma raporu geçersiz.")
    if type(entry_halted) is not bool:raise PilotError("Risk freni geçersiz.")
    if entry_halted:return hold("kill_switch")
    if state.get("position") or state.get("pending"):return hold("position_or_pending")
    label=report.get("research_label")
    if label not in ("research_up","research_down") or report.get("blockers")!=[]:
        return hold("consensus_not_confirmed")
    if not 0<=(now-stocks.ts(report["evaluated_at"])).total_seconds()<=30:
        return hold("stale_consensus")
    q=state.get("quote")
    if not fut.fresh(q,now):return hold("stale_quote")
    if q.get("source")!="binance-usdm-public":return hold("quote_source_mismatch")
    if abs((stocks.ts(q["source_at"])-stocks.ts(report["evaluated_at"])).total_seconds())>10:
        return hold("quote_report_time_mismatch")
    if not fut.entry_gate(q):return hold("pilot_entry_gate")
    # No open position: equity is cash. Never invent a daily baseline.
    e=amount(state["cash"]);peak=amount(state["peak"],"0.00000001")
    daily=amount(state["day_equity"],"0.00000001")
    if state.get("day")!=now.date().isoformat():return hold("daily_baseline_missing")
    if e>peak:raise PilotError("Zirve bakiye tutarsız.")
    daily_room=e-daily*D(".97");drawdown_room=e-peak*D(".90")
    if min(e,daily_room,drawdown_room)<=0:return hold("capital_brake")
    risk=report["risk_context"]
    atr1=amount(risk["atr_pct"]["1m"],hi="100")/100
    atr5=amount(risk["atr_pct"]["5m"],hi="100")/100
    side="LONG" if label=="research_up" else "SHORT";direction=D(1) if side=="LONG" else D(-1)
    adverse="downside_semivariance_20" if side=="LONG" else "upside_semivariance_20"
    semi=max(amount(risk["directional_semivariance"][f][adverse],hi="100") for f in ("1m","5m")).sqrt()
    funding=abs(amount(risk["reported_funding_rate"],"-.1",".1"))
    # Separate conservative stop distance from risk budget, no risk increase in calm markets.
    volatility=max(atr1,atr5,semi)
    stop_pct=max(D(".005"),D(2)*volatility)
    if stop_pct>fut.STOP:return hold("volatility_exceeds_stop_cap")
    scale=min(D(1),D(".01")/max(volatility,D(".01")))
    budget=min(e*fut.RISK*scale,daily_room,drawdown_room)
    leverage=min(LEVERAGE,D(1) if volatility>=D(".02") else LEVERAGE)
    bid,ask,mark=(stocks.dec(q[k]) for k in ("bid","ask","mark"))
    entry=(ask if side=="LONG" else bid)*(1+direction*SLIP)
    stop=entry*(1-direction*stop_pct)
    target=entry*(1+direction*min(fut.TARGET,stop_pct*2))
    # Model a full spread and twice normal slippage on the stop exit, plus two funding events.
    spread=(ask-bid)/((ask+bid)/2)
    exit_stop=stop*(1-direction*(2*SLIP+spread))
    if exit_stop<=0:return hold("invalid_stressed_stop")
    funding_reserve=2*max(funding,D(".001"))*max(entry,exit_stop)
    unit_loss=abs(entry-exit_stop)+FEE*(entry+exit_stop)+funding_reserve
    # A stop must lie on the safe side of the simplified isolated liquidation boundary.
    liq=(entry-entry/leverage+funding_reserve)/(1-MMR-FEE) if side=="LONG" else (entry+entry/leverage-funding_reserve)/(1+MMR+FEE)
    if side=="LONG" and exit_stop<=liq or side=="SHORT" and exit_stop>=liq:
        return hold("stop_liquidation_buffer")
    depth=min(amount(q["bid_depth_usdt"]),amount(q["ask_depth_usdt"]))
    qty=min(budget/unit_loss,e*fut.MARGIN_CAP*leverage/entry,
            e/(entry*(1/leverage+FEE)),depth/max(entry,exit_stop,ask)).quantize(D(".000001"),rounding=ROUND_DOWN)
    if qty<=0:return hold("quantity_below_model_step")
    notional=qty*entry;margin=notional/leverage
    out.update(status="research_proposal",quote_reference={"source":q["source"],"source_at":q["source_at"],"mid":str((bid+ask)/2)},proposal={"side":side,"quantity":str(qty),"entry":str(entry),
        "stop_price":str(stop),"target_price":str(target),"stop_distance_pct":str(stop_pct*100),
        "target_distance_pct":str(min(fut.TARGET,stop_pct*2)*100),"leverage_cap":str(leverage),
        "notional_usdt":str(notional),"margin_usdt":str(margin),"risk_budget_usdt":str(budget),
        "modeled_stressed_stop_loss_usdt":str(qty*unit_loss),"funding_reserve_usdt":str(qty*funding_reserve),
        "daily_loss_room_usdt":str(daily_room),"drawdown_room_usdt":str(drawdown_room),
        "volatility_scale":str(scale),"adverse_semideviation_pct":str(semi*100),
        "simplified_liquidation_price":str(liq),"exchange_lot_size_verified":False,
        "maximum_realized_loss_guaranteed":False})
    return out

def run(*,clock=stocks.utc):
    if os.getenv("CYBERBOT_FUTURES_DYNAMIC_RISK_ENABLED")!="1" or not fut.enabled():
        raise PilotError("Dinamik risk araştırma izni kapalı.")
    report=consensus.run(clock=clock)
    sym=fut.symbol();p=stocks.path()
    if not p.is_file():raise PilotError("Futures pilot kaydı yok.")
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
        if not db.execute("SELECT 1 FROM observed_accounts WHERE market='FUTURES'").fetchone():
            raise PilotError("Futures pilot kaydı yok.")
        state=fut.load(db,sym);stop=halted(db)
        return evaluate(state,report,clock(),entry_halted=stop)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.parse_args()
    try:print(json.dumps(run(),ensure_ascii=True));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__}));return 1
if __name__=="__main__":raise SystemExit(main())
