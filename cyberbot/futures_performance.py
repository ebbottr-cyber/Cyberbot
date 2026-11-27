"""Read-only observed Futures PAPER ledger performance, not exchange fills."""
import argparse,json,sqlite3
from contextlib import closing
from decimal import Decimal as D
from . import futures_pilot as fut,observed_pilot as stocks,db_paths

VERSION="futures-performance-1"
MAX_EVENTS=250000
ZERO=D(0)
def dec(x):
    return fut.number(x,"-1000000000000","1000000000000")
def money(x):return str(x) if x is not None else None
def summary(trades):
    pnls=[t["pnl"] for t in trades];n=len(pnls)
    gross_profit=sum((p for p in pnls if p>0),ZERO)
    gross_loss=-sum((p for p in pnls if p<0),ZERO)
    wins=sum(p>0 for p in pnls);losses=sum(p<0 for p in pnls)
    return {"closed_trades":n,"wins":wins,"losses":losses,"breakeven":n-wins-losses,
            "win_rate_pct":money(D(wins)*100/n if n else None),
            "net_pnl_usdt":money(sum(pnls,ZERO)),
            "positive_net_trade_sum_usdt":money(gross_profit),"negative_net_trade_sum_abs_usdt":money(gross_loss),
            "profit_factor":money(gross_profit/gross_loss if gross_loss else None),
            "average_net_pnl_usdt":money(sum(pnls,ZERO)/n if n else None),
            "entry_fees_usdt":money(sum((t["entry_fee"] for t in trades),ZERO)),
            "modeled_exit_fees_charged_usdt":money(sum((t["exit_fee"] for t in trades),ZERO)),
            "funding_net_usdt":money(sum((t["funding"] for t in trades),ZERO)),
            "liquidations":sum(t["liquidated"] for t in trades)}
def decline(value,peak,maximum):
    peak=max(value,peak)
    return peak,max(maximum,(peak-value)/peak*100 if peak>0 else ZERO)
def replay(rows,state,now):
    cash=D(fut.START);realized=cash;rp=ep=cash;rd=ed=ZERO
    pos=None;trades=[];fees=ZERO;funding=ZERO;fills=liqs=funding_count=gap_count=0
    quote=None;last=None;samples=0;gap_samples=0
    for event_id,recorded,event,payload in rows:
        d=json.loads(payload);q=d.get("quote")
        if q is None:
            if event in ("open_fill","close_fill","model_liquidation"):raise ValueError("Eksik işlem gözlemi.")
            continue
        at=stocks.ts(q["source_at"]);received=stocks.ts(recorded)
        if not at<=received<=now or (received-at).total_seconds()>fut.MAX_AGE or (last and at<=last):
            raise ValueError("Gözlem zaman sırası uyuşmuyor.")
        gap=bool(pos and last and (at-last).total_seconds()>fut.MAX_AGE)
        if gap:gap_count+=1
        last=at;quote=q
        applied=d.get("funding_applied",[])
        if applied and pos is None:raise ValueError("Pozisyonsuz fonlama.")
        for item in applied:
            amount=dec(item["amount_usdt"]);pos["funding"]+=amount;funding+=amount;funding_count+=1
        r=d.get("result",{})
        if event=="open_fill":
            if pos is not None:raise ValueError("Çift giriş.")
            if r["side"] not in ("LONG","SHORT") or r.get("origin","manual") not in ("manual","ai_auto"):raise ValueError("İşlem kimliği.")
            pos={**r,"qty":dec(r["qty"]),"entry":dec(r["entry"]),"margin":dec(r["margin"]),
                 "entry_fee":dec(r["entry_fee"]),"funding":dec(r["funding"])}
            if min(pos["qty"],pos["entry"],pos["margin"])<=0 or pos["entry_fee"]<0 or pos["funding"]!=0:
                raise ValueError("Giriş miktarları.")
            cash-=pos["margin"]+pos["entry_fee"];fees+=pos["entry_fee"];fills+=1
        elif event in ("close_fill","model_liquidation"):
            if pos is None:raise ValueError("Girişsiz çıkış.")
            liq=event=="model_liquidation";price=dec(r["observed_price"])
            if price<=0 or dec(r["funding"])!=pos["funding"]:raise ValueError("Çıkış fonlama/fiyatı.")
            residual=pos["margin"]+pos["qty"]*(D(1) if pos["side"]=="LONG" else D(-1))*(price-pos["entry"])+pos["funding"]
            # Liquidation forfeits isolated margin, with no separately charged exit fee.
            charged=ZERO if liq else min(max(ZERO,residual),pos["qty"]*price*fut.FEE)
            recovered=ZERO if liq else max(ZERO,residual-charged)
            pnl=recovered-pos["margin"]-pos["entry_fee"]
            if pnl!=dec(r["pnl"]):raise ValueError("Net kâr-zarar mutabakatı.")
            cash+=recovered;realized+=pnl;fees+=charged
            rp,rd=decline(realized,rp,rd)
            trades.append({"origin":pos.get("origin","manual"),"side":pos["side"],"pnl":pnl,
                           "entry_fee":pos["entry_fee"],"exit_fee":charged,"funding":pos["funding"],
                           "liquidated":liq,"closed_at":received.isoformat(),"reason":r.get("reason","unknown")})
            if liq:liqs+=1
            else:fills+=1
            pos=None
        if pos:
            direction=D(1) if pos["side"]=="LONG" else D(-1)
            book=dec(q["bid"] if direction>0 else q["ask"])
            depth=dec(q["bid_depth_usdt"] if direction>0 else q["ask_depth_usdt"])
            if pos["qty"]*book>depth:
                gap_samples+=1;continue
            exit_price=book*(1-direction*fut.SLIP)
            value=cash+max(ZERO,pos["margin"]+pos["qty"]*direction*(exit_price-pos["entry"])+pos["funding"]-pos["qty"]*exit_price*fut.FEE)
        else:value=cash
        ep,ed=decline(value,ep,ed);samples+=1
    if (cash!=dec(state["cash"]) or fills!=state["fills"] or liqs!=state["liquidations"] or
        funding_count!=state["funding_events"] or gap_count!=state["gap_count"] or bool(pos)!=bool(state["position"]) or quote!=state["quote"]):
        raise ValueError("Olay geçmişi ile kasa uyuşmuyor.")
    if pos:
        for k in ("qty","entry","margin","entry_fee","funding"):
            if pos[k]!=dec(state["position"][k]):raise ValueError("Açık pozisyon uyuşmuyor.")
        for k in ("side","opened_at","origin"):
            if pos.get(k)!=state["position"].get(k):raise ValueError("Açık pozisyon kimliği.")
    current_equity=None;reason=None
    if not fut.fresh(quote,now):reason="stale_quote"
    elif pos and fut.boundaries(quote["source_at"],now.isoformat()):reason="funding_due"
    elif pos and pos["qty"]*dec(quote["bid"] if pos["side"]=="LONG" else quote["ask"])>dec(quote["bid_depth_usdt"] if pos["side"]=="LONG" else quote["ask_depth_usdt"]):reason="insufficient_exit_depth"
    else:current_equity=fut.equity(state)
    total=summary(trades)
    return {"closed":total,"by_origin":{k:summary([t for t in trades if t["origin"]==k]) for k in ("manual","ai_auto")},
            "by_side":{k:summary([t for t in trades if t["side"]==k]) for k in ("LONG","SHORT")},
            "initial_capital_usdt":money(D(fut.START)),"realized_balance_usdt":money(realized),"available_cash_usdt":money(cash),
            "current_modeled_equity_usdt":money(current_equity),"equity_unavailable_reason":reason,
            "open_position_unrealized_net_usdt":money(current_equity-realized if current_equity is not None and pos else None),
            "realized_return_pct":money((realized/D(fut.START)-1)*100),"realized_max_drawdown_pct":money(rd),
            "sampled_equity_max_drawdown_pct":money(ed if samples else None),"equity_samples":samples,"depth_skipped_samples":gap_samples,
            "position_observation_gaps":gap_count,"total_fees_including_open_usdt":money(fees),"total_funding_including_open_usdt":money(funding),
            "open_position":bool(pos),"event_rows":len(rows),"ledger_reconciled":True,
            "recent_closed":[{k:money(v) if isinstance(v,D) else v for k,v in t.items()} for t in trades[-20:][::-1]]}

def report(symbol,*,clock=stocks.utc):
    if symbol not in ("BTCUSDT","ETHUSDT"):raise ValueError("Sembol geçersiz.")
    db_paths.checked();p=db_paths.pilot_path();now=clock()
    out={"version":VERSION,"symbol":symbol,"status":"not_initialized","currency":"USDT","as_of":now.isoformat(),
         "real_orders":False,"exchange_execution_verified":False,"profitability_verified":False,
         "continuous_drawdown_verified":False,"model":"observed_paper","metrics":None}
    if not p.is_file():return out
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"observed_accounts","observed_events"}<=tables:raise ValueError("Pilot şeması eksik.")
        if not db.execute("SELECT 1 FROM observed_accounts WHERE market='FUTURES'").fetchone():return out
        s=fut.load(db,symbol)
        rows=db.execute("SELECT id,at,event,payload FROM observed_events WHERE market='FUTURES' ORDER BY id LIMIT ?",(MAX_EVENTS+1,)).fetchall()
        if len(rows)>MAX_EVENTS:return {**out,"status":"event_limit_exceeded"}
        out.update(status="read_only",metrics=replay(rows,s,now))
    return out
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--symbol",required=True,choices=("BTCUSDT","ETHUSDT"));a=p.parse_args()
    try:print(json.dumps(report(a.symbol),ensure_ascii=True,allow_nan=False));return 0
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,sqlite3.Error) as e:
        print(json.dumps({"status":"rejected","type":type(e).__name__,"metrics":None,"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
