"""Synthetic data only. No network calls."""
from decimal import Decimal
from dataclasses import dataclass

D = Decimal

@dataclass(frozen=True)
class Instrument:
    market: str
    symbol: str
    prices: tuple[Decimal, ...]

def instrument(market, symbol, prices):
    return Instrument(market, symbol, tuple(D(str(x)) for x in prices))

INSTRUMENTS = (
    instrument("BIST", "DEMO-BIST", [100, 102, 101, 104, 105, 101, 98, 104, 107, 110]),
    instrument("NASDAQ", "DEMO-NASDAQ", [200, 198, 201, 205, 206, 208, 204, 201, 210, 214]),
    instrument("XETRA", "DEMO-XETRA", [80, 81, 83, 82, 85, 84, 79, 80, 86, 88]),
    instrument("SOLANA", "DEMO-SOL", [1, 1.04, 1.08, 1.02, 0.95, 1.13, 1.18, 1.05, 1.25, 1.3]),
)
INDEX = {i.symbol: i for i in INSTRUMENTS}

def quote(symbol, tick):
    prices = INDEX[symbol].prices
    return prices[min(tick, len(prices)-1)]
