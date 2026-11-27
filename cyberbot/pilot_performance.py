"""Read-only observed paper reporting. No synthetic ledger, provider calls or new fills."""
import json,sqlite3
from contextlib import closing
from decimal import Decimal as D
from . import observed_pilot as stocks,solana_pilot as sol,futures_pilot as fut
from .observed_pilot import PilotError
from .pilot_control import halted

MARKETS=("BIST","NASDAQ","XETRA","SOLANA","FUTURES")
MAX_EVENTS=5000
FILL_EVENTS=("buy_fill","sell_fill","open_fill","close_fill","model_liquidation")
def money(x):return str(x.quantize(D(".000001")))
def base(m):
    cur="TRY" if m=="BIST" else "USDT" if m=="FUTURES" else "USD"
    return {"market":m,"currency":cur,"initial_capital":"45000" if m=="BIST" else "1000","status":"disabled","equity":None,"cash":None,"position_open":None,"pending":None,"current_drawdown_pct":None,"daily_pnl":None,"risk_gate":None,"statistics":None,"recent":[]}
def summarize(m,events):
    # Full fill/funding stream, not just the visible latest rows. Reject inconsistent pairs.
    opened=None;closed=0;wins=0;losses=0;net=D(0);fees=D(0);funding=D(0);liqs=0;fee_unknown=0;recent=[]
    for stamp,event,payload in events:
        d=json.loads(payload);res=d.get("result",{})
        if m=="FUTURES":
            for x in d.get("funding_applied",[]):funding+=D(x["amount_usdt"])
        if event not in FILL_EVENTS:continue
        row={"at":stamp,"event":event,"pnl":None,"reason":res.get("reason"),"nominal_fee":None}
        if event in ("buy_fill","open_fill"):
            if opened is not None:raise PilotError("Çakışan açılış kaydı.")
            opened=res
            if m=="FUTURES":fee=D(res["entry_fee"])
            elif m=="SOLANA":fee=D(res["qty"])*D(res["entry"])*sol.FEE+sol.FIXED
            else:fee=D(res["quantity"])*D(res["entry"])*D(res.get("entry_conversion_rate","1"))*stocks.FEE
            fees+=fee;row["nominal_fee"]=money(fee)
        else:
            if opened is None:raise PilotError("Eksik açılış kaydı.")
            pnl=D(res["pnl"]);net+=pnl;closed+=1;wins+=int(pnl>0);losses+=int(pnl<0)
            row["pnl"]=money(pnl)
            if event=="model_liquidation":
                liqs+=1;fee_unknown+=1 # forfeited margin is not a separately identified commission
            else:
                if m=="FUTURES":fee=D(opened["qty"])*D(res["observed_price"])*fut.FEE
                elif m=="SOLANA":fee=D(opened["qty"])*D(res["exit"])*sol.FEE+sol.FIXED
                else:fee=D(res["quantity"])*D(res["exit"])*D(res.get("exit_conversion_rate","1"))*stocks.FEE
                fees+=fee;row["nominal_fee"]=money(fee)
            opened=None
        recent.append(row)
    return {"closed":closed,"wins":wins,"losses":losses,"flat":closed-wins-losses,"win_pct":money(D(wins)*100/closed) if closed else None,"realized_pnl":money(net),"nominal_fees":money(fees),"unitemized_liquidation_fees":fee_unknown,"net_applied_funding":money(funding) if m=="FUTURES" else None,"liquidations":liqs,"open_event_exists":opened is not None},recent[-20:][::-1]
def snapshot(*,clock=stocks.utc,markets=MARKETS):
    markets=tuple(markets)
    if len(set(markets))!=len(markets) or any(m not in MARKETS for m in markets):raise ValueError("Geçersiz piyasa kapsamı.")
    now=clock();result={"mode":"operator_observed_unverified","as_of":now.isoformat(),"markets":[base(m) for m in markets],"real_orders":False,"live_data_verified":False,"profitability_verified":False,"combined_equity":None,"limits":["Sentetik kasalar dahil değil. Para birimleri ayrı; toplam üretilmez.","Komisyonlar modeldeki nominal ücretlerdir; kayma fiyatlara dahildir. Likidasyonda ayrıştırılamayan ücret olabilir.","Gerçekleşen K/Z model kapanış kayıtlarından, fonlama uygulanan olaylardan. Günlük K/Z UTC gününe ait ilk gözleme göredir; tam günlük veri değil.","Geçerli fiyat, derinlik veya fonlama yoksa güncel K/Z ve düşüş gösterilmez. En fazla 5000 muhasebe olayı/piyasa (dolum ve uygulanan fonlama); aşımda istatistik gösterilmez."]}
    p=stocks.path()
    if not stocks.permitted():return result
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=3)) if p.is_file() else closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
        tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for item in result["markets"]:
            m=item["market"]
            if m=="XETRA" and not stocks.fx_permitted():continue
            if m=="SOLANA" and not sol.enabled():continue
            if m=="FUTURES" and not fut.enabled():continue
            item["status"]="not_initialized"
            if m=="SOLANA":
                try:mint,pool=sol.config()
                except PilotError:item["status"]="configuration_missing";continue
                item["symbol"]=mint
            elif m=="FUTURES":
                try:sym=fut.symbol()
                except PilotError:item["status"]="configuration_missing";continue
                item["symbol"]=sym
            else:item["symbol"]=stocks.account(m)[0]
            if not {"observed_accounts","observed_events"}.issubset(tables) or not db.execute("SELECT 1 FROM observed_accounts WHERE market=?",(m,)).fetchone():continue
            try:
                s=sol.load(db,mint,pool) if m=="SOLANA" else fut.load(db,sym) if m=="FUTURES" else stocks.load(db,m)
                q=s["quote"];pos=s["position"]
                if m=="SOLANA":
                    valid=sol.fresh(q,now) and (not pos or D(pos["qty"])*D(q["bid"])<=D(q["bid_depth_usd"]))
                    value=sol.mark(s);gate=sol.risk_ok(s) and sol.entry_gate(q,now)
                elif m=="FUTURES":
                    depth=not pos or D(pos["qty"])*D(q["bid"] if fut.sign(pos)>0 else q["ask"])<=D(q["bid_depth_usdt"] if fut.sign(pos)>0 else q["ask_depth_usdt"])
                    due=bool(pos and int(now.timestamp()//fut.FUNDING_PERIOD)>int(stocks.ts(q["source_at"]).timestamp()//fut.FUNDING_PERIOD))
                    valid=fut.fresh(q,now) and depth and not due;value=fut.equity(s);gate=fut.risk_ok(s) and fut.entry_gate(q)
                else:
                    valid=stocks.fresh(q,now,m) and (not pos or "bid_size" not in q or D(pos["quantity"])<=D(q["bid_size"]));value=stocks.equity(s);gate=not stocks.blocked(s)
                item.update(status="recorded" if valid else "valuation_unavailable",cash=money(D(s["cash"])),equity=money(value) if valid else None,position_open=bool(pos),pending=s["pending"],current_drawdown_pct=money((1-value/D(s["peak"]))*100) if valid else None,daily_pnl=money(value-D(s["day_equity"])) if valid and s["day"]==now.date().isoformat() else None,risk_gate=bool(gate and not halted(db) and not pos and not s["pending"]) if valid and s["day"]==now.date().isoformat() else None)
                count=db.execute("SELECT count(*) FROM observed_events WHERE market=?",(m,)).fetchone()[0]
                item["event_count"]=count
                # Price-only observations and shadow decisions must not consume the
                # accounting limit. Include all fills and applied funding, in order.
                relevant="market=? AND (event IN ('buy_fill','sell_fill','open_fill','close_fill','model_liquidation')"
                if m=="FUTURES":relevant+=" OR json_array_length(payload,'$.funding_applied')>0"
                relevant+=")"
                events=db.execute("SELECT at,event,payload FROM observed_events WHERE "+relevant+" ORDER BY id LIMIT ?",(m,MAX_EVENTS+1)).fetchall()
                item["accounting_event_count"]=len(events)
                if len(events)>MAX_EVENTS:item["history_status"]="scope_limit";continue
                stats,recent=summarize(m,events)
                if bool(pos)!=stats.pop("open_event_exists"):raise PilotError("Pozisyon ve olay geçmişi tutarsız.")
                if not pos and abs(D(s["cash"])-D(item["initial_capital"])-D(stats["realized_pnl"]))>D(".000002"):raise PilotError("Kasa ve kapanış kayıtları tutarsız.")
                item.update(statistics=stats,recent=recent,history_status="recorded")
            except (ValueError,KeyError,TypeError,ArithmeticError):
                item.update(status="review_required",equity=None,daily_pnl=None,current_drawdown_pct=None,risk_gate=None,statistics=None,recent=[])
    return result
