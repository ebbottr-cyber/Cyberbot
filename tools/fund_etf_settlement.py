"""Product-specific historical paper replay; explicit calendar and rules required.

End-of-session convention: submissions, price publication, settlement,
then dividend eligibility and payment. No real orders, taxes or splits.
"""
import math
from datetime import date, datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo


def number(value, *, positive=False):
    v = Decimal(str(value))
    if not v.is_finite() or v < 0 or (positive and v <= 0):
        raise ValueError("invalid_amount")
    return v


def replay(*, market, symbol, currency, rules, sessions, prices, orders,
           as_of, initial_cash, initial_units=0, dividends=()):
    """Single instrument, one currency, caller-supplied historical inputs.

    sessions: [{date, cutoff}] sorted explicit trading/settlement sessions.
    prices: {price_session: observed close or NAV}; publication lag from rules.
    orders: [{id, timestamp (offset required), side, amount}].
    BUY amount = cash budget inclusive of fees; SELL amount = settled units.
    dividends: [{record_session,pay_session,net_per_unit,source}].
    Rule lags count supplied sessions from effective order session.
    """
    if market not in ("TEFAS", "ETF") or currency not in ("TRY","USD","EUR","GBP") or (market=="TEFAS" and currency!="TRY") or not symbol:
        raise ValueError("invalid_instrument")
    if not str(rules.get("source","")).strip() or not str(rules.get("calendar_source","")).strip():
        raise ValueError("rule_and_calendar_provenance_required")
    if rules.get("corporate_actions_reviewed") is not True:
        raise ValueError("corporate_actions_review_required")
    end = date.fromisoformat(as_of)
    zone = timezone.utc if rules["timezone"]=="UTC" else ZoneInfo(rules["timezone"])
    if end > datetime.now(zone).date():
        raise ValueError("future_replay")
    days = [date.fromisoformat(s["date"]) for s in sessions]
    if not days or days != sorted(set(days)):
        raise ValueError("invalid_calendar")
    valid_from = date.fromisoformat(rules["valid_from"])
    valid_to = date.fromisoformat(rules["valid_to"])
    if not valid_from <= days[0] <= end <= valid_to:
        raise ValueError("rules_outside_validity")
    if days[-1] > valid_to:
        raise ValueError("calendar_outside_rule_validity")
    cutoffs = [time.fromisoformat(s["cutoff"]) for s in sessions]
    if any(t.tzinfo is not None for t in cutoffs):
        raise ValueError("cutoff_must_be_local")
    idx = {d:i for i,d in enumerate(days)}
    # Separate assumptions for buys and sells; no universal TEFAS valör.
    for side in ("buy","sell"):
        lags = [rules[side+"_"+k] for k in ("price_lag","publication_lag","settlement_lag")]
        if any(type(x) is not int or not 0 <= x <= 30 for x in lags):
            raise ValueError("invalid_lag")
        if lags[2] < lags[0]+lags[1]:
            raise ValueError("settlement_precedes_price_publication")
    fee = number(rules["fee_bps"])/10000
    if fee >= 1:
        raise ValueError("invalid_fee")
    cash, units = number(initial_cash), number(initial_units)
    starting_cash, starting_units = cash, units
    reserved_cash = reserved_units = Decimal(0)
    # Do not consume observations whose configured publication is in the future.
    observations = {date.fromisoformat(k):v for k,v in prices.items()}
    if any(d not in idx for d in observations):
        raise ValueError("price_outside_calendar")
    pending, events, queue, entitlements = [], [], {}, []
    seen = set()
    for order in orders:
        stamp = datetime.fromisoformat(order["timestamp"])
        if stamp.tzinfo is None or not order["id"] or order["id"] in seen or order["side"] not in ("BUY","SELL"):
            raise ValueError("invalid_order")
        seen.add(order["id"])
        local = stamp.astimezone(zone)
        if not days[0] <= local.date() <= end:
            raise ValueError("order_outside_replay")
        amount = number(order["amount"], positive=True)
        queue.setdefault(local.date(),[]).append((local,order,amount))
    distributions = {}
    if dividends and market != "ETF":
        raise ValueError("dividends_only_supported_for_etf")
    for div in dividends:
        record, pay = (date.fromisoformat(div[k]) for k in ("record_session","pay_session"))
        if record not in idx or pay not in idx or pay < record or not str(div.get("source","")).strip():
            raise ValueError("invalid_dividend")
        distributions.setdefault(record,[]).append((pay,number(div["net_per_unit"]),div["source"]))
    def emit(day, kind, **fields):
        events.append(dict(date=day.isoformat(),event=kind,**fields))
    timeline = sorted((set(days)|set(queue)) & {d for d in set(days)|set(queue) if d <= end})
    for day in timeline:
        for stamp,order,amount in sorted(queue.get(day,[]),key=lambda x:(x[0],x[1]["id"])):
            side = order["side"].lower()
            effective = next((i for i,d in enumerate(days) if d>day or (d==day and stamp.time()<cutoffs[i])),None)
            if effective is None:
                emit(day,"rejected",id=order["id"],reason="calendar_missing"); continue
            pricing = effective+rules[side+"_price_lag"]
            publish = pricing+rules[side+"_publication_lag"]
            settle = effective+rules[side+"_settlement_lag"]
            if max(pricing,publish,settle)>=len(days):
                emit(day,"rejected",id=order["id"],reason="calendar_missing"); continue
            if (side=="buy" and amount>cash) or (side=="sell" and amount>units):
                emit(day,"rejected",id=order["id"],reason="insufficient_available_balance"); continue
            if side=="buy":
                cash-=amount; reserved_cash+=amount
            else:
                units-=amount; reserved_units+=amount
            pending.append(dict(id=order["id"],side=side,amount=amount,
                                pricing=days[pricing],publish=days[publish],settle=days[settle],state="awaiting_price"))
            emit(day,"accepted",id=order["id"],effective_session=days[effective].isoformat(),
                 pricing_session=days[pricing].isoformat(),publication_session=days[publish].isoformat(),
                 settlement_session=days[settle].isoformat())
        for item in pending:
            if item["state"]=="awaiting_price" and day==item["publish"]:
                if item["pricing"] not in observations:
                    item["state"]="blocked_missing_price"
                    emit(day,"blocked",id=item["id"],reason="missing_published_price")
                    continue
                p = number(observations[item["pricing"]],positive=True)
                a = item["amount"]
                gross = a/(1+fee) if item["side"]=="buy" else a*p
                item.update(state="priced",price=p,fee=gross*fee,
                            received=gross/p if item["side"]=="buy" else gross*(1-fee))
                emit(day,"priced",id=item["id"],price=str(p),fee=str(item["fee"]))
            if item["state"]=="priced" and day==item["settle"]:
                if item["side"]=="buy":
                    reserved_cash-=item["amount"]; units+=item["received"]
                else:
                    reserved_units-=item["amount"]; cash+=item["received"]
                item["state"]="settled"
                emit(day,"settled",id=item["id"],received=str(item["received"]))
        for pay,net,source in distributions.get(day,[]):
            # Explicit simplified record-session convention; exclude unsettled buys,
            # include reserved sells until settlement. No inferred ex-date entitlement.
            amount = (units+reserved_units)*net
            entitlements.append(dict(pay=pay,amount=amount,paid=False))
            emit(day,"dividend_record",amount=str(amount),source=source)
        for ent in entitlements:
            if ent["pay"]==day and not ent["paid"]:
                cash+=ent["amount"]; ent["paid"]=True
                emit(day,"dividend_paid",amount=str(ent["amount"]))
    active = [p for p in pending if p["state"]!="settled"]
    # Do not value unresolved trades or infer an unpublished closing price.
    eligible=[d for d in observations if idx[d]+max(rules["buy_publication_lag"],rules["sell_publication_lag"])<len(days)
              and days[idx[d]+max(rules["buy_publication_lag"],rules["sell_publication_lag"])]<=end]
    pnl=None
    if not active and not any(not e["paid"] for e in entitlements) and eligible and days[0] in observations:
        latest=max(eligible)
        first=number(observations[days[0]],positive=True)
        last=number(observations[latest],positive=True)
        basis=starting_cash+starting_units*first
        marked=cash+units*last
        pnl=dict(mark_session=latest.isoformat(),initial_equity=str(basis),
                 marked_equity=str(marked),profit_loss=str(marked-basis),
                 return_pct=str((marked/basis-1)*100) if basis>0 else None,
                 actual_account_pnl=False)
    return dict(pnl=pnl,status="review_required" if any(p["state"].startswith("blocked") for p in active) else "paper_replay",
                market=market,symbol=symbol,currency=currency,as_of=as_of,
                initial_cash=str(starting_cash),initial_units=str(starting_units),
                available_cash=str(cash),available_units=str(units),
                reserved_cash=str(reserved_cash),reserved_units=str(reserved_units),
                pending=[dict(id=p["id"],state=p["state"],settlement_session=p["settle"].isoformat()) for p in active],
                events=events,rule_source=rules["source"],calendar_source=rules["calendar_source"],
                rules_independently_verified=False,calendar_independently_verified=False,
                dividends_independently_verified=False,settlement_verified=False,
                real_orders=False,execution_allowed=False)
