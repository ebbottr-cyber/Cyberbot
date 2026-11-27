"""Bounded anonymous quote-size diagnostics; not a liquidity attestation or paper fill."""
import argparse,json,os,time
from decimal import Decimal as D
from tools.solana_route_preview import run as preview
from cyberbot.solana_pilot import address
from cyberbot.providers.solana_observed import PilotError,USDC
from cyberbot.observed_pilot import utc

SIZES=(25,50,100)
def run(mint,*,probe=preview,sleep=time.sleep):
    if os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED")!="1":
        raise PilotError("Explicit data usage permission required")
    if not address(mint) or mint==USDC:raise PilotError("Invalid mint")
    rows=[]
    for size in SIZES:
        try:
            d=probe(mint,amount=size*10**6)
            rows.append({"status":"ok","input_usdc":size,"retrieved_at":d["retrieved_at"],
                         "reported_return_usdc":d["reported_roundtrip_return_usdc"],
                         "reported_roundtrip_pct":d["reported_roundtrip_pct"],
                         "buy_route":d["buy"]["route_kind"],"sell_route":d["sell"]["route_kind"],
                         "buy_accounting":d["buy"]["accounting"],"sell_accounting":d["sell"]["accounting"],
                         "buy_fee_bps":d["buy"]["reported_fee_bps"],"sell_fee_bps":d["sell"]["reported_fee_bps"],
                         "buy_fee_mint":d["buy"]["reported_fee_mint"],"sell_fee_mint":d["sell"]["reported_fee_mint"]})
        except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AttributeError) as e:
            rows.append({"status":"rejected","input_usdc":size,"reason":str(e) if isinstance(e,PilotError) else type(e).__name__})
            break # No burst retry or further probing after a provider error.
        if size!=SIZES[-1]:sleep(5)
    return {"status":"probe_complete" if len(rows)==len(SIZES) and all(r["status"]=="ok" for r in rows) else "probe_partial",
            "mint":mint,"retrieved_at":utc().isoformat(),"samples":rows,
            "sequential_not_simultaneous":True,"depth_verified":False,"route_integrity_verified":False,
            "security_verified":False,"live_data_verified":False,"pilot_applied":False,"real_orders":False,"api_key_used":False}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--mint",required=True);args=p.parse_args()
    try:
        d=run(args.mint);print(json.dumps(d,indent=2));return 0 if d["status"]=="probe_complete" else 1
    except PilotError as e:
        print(json.dumps({"status":"rejected","reason":str(e),"real_orders":False}));return 1
if __name__=="__main__":raise SystemExit(main())
