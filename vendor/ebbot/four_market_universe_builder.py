#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a provenance-aware three-exchange EQUITY candidate list, without trades.

Yahoo Finance offers quotes but no authoritative all-exchange symbol directory.
Use the EBBot 300 as a floor, optionally refresh Nasdaq from its
official public directory, and import additional exchange-vetted market,symbol
CSV files. Listings are *candidates*, not verified Yahoo coverage. A separate
read-only grouped scanner validates each candidate against daily OHLCV.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

MARKETS = ("tr", "us", "de")
NASDAQ_DIRECTORY_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
KAP_BIST_LIST_URL = "https://www.kap.org.tr/tr/bist-sirketler"
HKEX_DIRECTORY_URL = "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx"
XETRA_DIRECTORY_URL = "https://www.cashmarket.deutsche-boerse.com/resource/blob/1528/860eeaf32f378fd523653e9c3b0842e5/data/t7-xetr-allTradableInstruments.csv"
DEFAULT_SEED = Path(__file__).resolve().parent / "four_market_universe_100.csv"
_MAX_DIRECTORY_BYTES = 4 * 1024 * 1024
_US_SYMBOL = re.compile(r"^[A-Z][A-Z0-9]{0,4}$")
_EQUITY_SUFFIX = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,14}$")
_HK_SYMBOL = re.compile(r"^[0-9]{1,5}$")
_NON_EQUITY_LABELS = (
    "preferred", "preference", "depositary note", "notes due", "senior notes",
    "subordinated notes", "exchange traded fund", "exchange-traded fund",
    "closed end fund", "closed-end fund", "debenture",
    "subscription receipt",
)
# Boundary-aware: a substring test for 'unit' wrongly excludes United
# Airlines and Community shares. ADR/ADS are not inherently non-equity.
_NON_EQUITY_WORDS = re.compile(r"\b(?:warrants?|rights?|units?|etfs?|etns?)\b")


def canonical_equity(market: str, symbol: str) -> str:
    """Never invent Yahoo tickers from names/ISINs or mix exchange suffixes."""
    market = str(market).strip().lower()
    raw = str(symbol or "").strip().upper()
    if market not in MARKETS:
        raise ValueError(f"unsupported market {market!r}")
    if market == "tr" or market == "de":
        suffix = ".IS" if market == "tr" else ".DE"
        base = raw[:-len(suffix)] if raw.endswith(suffix) else raw
        if "." in base or not _EQUITY_SUFFIX.fullmatch(base):
            raise ValueError(f"invalid {market} equity {symbol!r}")
        normalized = base + suffix
        if normalized == "XU100.IS":
            raise ValueError("BIST 100 index is not an equity")
        return normalized
    if market == "us":
        if not _US_SYMBOL.fullmatch(raw):
            raise ValueError(f"unsupported Nasdaq Yahoo equity symbol {symbol!r}")
        return raw
    raise ValueError(f"unsupported market {market!r}")


def _canonical_historical_hk_equity(raw: str) -> str:
    """Legacy workbook parser only; not an active equity market."""
    symbol = raw
    raw = raw.strip().upper()
    if raw.startswith("HK") and raw[2:].isdigit():
        raw = raw[2:]
    if raw.endswith(".HK"):
        raw = raw[:-3]
    if not _HK_SYMBOL.fullmatch(raw) or int(raw) == 0:
        raise ValueError(f"invalid Hong Kong equity {symbol!r}")
    return str(int(raw)).zfill(4) + ".HK"


def parse_market_csv(payload: str, *, label: str) -> dict[str, list[str]]:
    reader = csv.DictReader(io.StringIO(payload.lstrip("\ufeff")))
    if not {"market", "symbol"}.issubset(reader.fieldnames or ()):
        raise ValueError(f"{label}: expected market,symbol headers")
    out = {market: [] for market in MARKETS}
    seen = {market: set() for market in MARKETS}
    for number, row in enumerate(reader, 2):
        market = str(row.get("market") or "").strip().lower()
        try:
            symbol = canonical_equity(market, row.get("symbol") or "")
        except ValueError as exc:
            raise ValueError(f"{label}:{number}: {exc}") from exc
        if symbol not in seen[market]:
            seen[market].add(symbol)
            out[market].append(symbol)
    return out


def parse_nasdaq_directory(payload: str) -> tuple[list[str], Counter]:
    """Official pipe-separated nasdaqlisted.txt; exclude ETFs and non-equities."""
    reader = csv.DictReader(io.StringIO(payload.lstrip("\ufeff")), delimiter="|")
    expected = {"Symbol", "Security Name", "ETF", "Test Issue"}
    if not expected.issubset(reader.fieldnames or ()):
        raise ValueError("Nasdaq directory headers changed; refusing to guess")
    found: set[str] = set()
    reasons: Counter = Counter()
    for row in reader:
        raw = str(row.get("Symbol") or "").strip().upper()
        name = str(row.get("Security Name") or "").lower()
        if raw.startswith("FILE CREATION TIME"):
            continue
        if row.get("Test Issue", "").strip().upper() != "N":
            reasons["test_or_unknown"] += 1
            continue
        if row.get("ETF", "").strip().upper() != "N":
            reasons["etf_or_unknown"] += 1
            continue
        if any(x in name for x in _NON_EQUITY_LABELS) or _NON_EQUITY_WORDS.search(name):
            reasons["non_equity_type"] += 1
            continue
        if not _US_SYMBOL.fullmatch(raw):
            reasons["unsupported_yahoo_symbol"] += 1
            continue
        found.add(raw)
    if not found:
        raise ValueError("Nasdaq official list contained no eligible equities")
    return sorted(found), reasons


def download_official_nasdaq(*, timeout: float = 20.0) -> str:
    """Hard-coded HTTPS host, bounded response size, fail closed on errors."""
    request = urllib.request.Request(
        NASDAQ_DIRECTORY_URL,
        headers={"User-Agent": "EBBot-ReadOnly-Universe/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.geturl().split("/")[2].lower() != "www.nasdaqtrader.com":
            raise ValueError("unexpected Nasdaq listing redirect host")
        payload = response.read(_MAX_DIRECTORY_BYTES + 1)
    if len(payload) > _MAX_DIRECTORY_BYTES:
        raise ValueError("Nasdaq listing exceeds permitted size")
    return payload.decode("utf-8-sig", errors="strict")


def parse_kap_bist_page(html: str) -> tuple[list[str], Counter]:
    """Read listed stockCode fields from KAP's embedded Next.js flight data.

    KAP membership is only an upstream candidate list. Do not equate a KAP
    record with an active Yahoo-tradable security.
    """
    frames: list[str] = []
    for matched in re.finditer(
        r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)',
        html,
    ):
        try:
            frames.append(json.loads(matched.group(1)))
        except (ValueError, TypeError):
            continue
    if not frames:
        raise ValueError("KAP Next.js membership data unavailable; fail closed")
    raw_codes = re.findall(r'"stockCode"\s*:\s*"([^"]+)"', "".join(frames))
    symbols: set[str] = set()
    rejected: Counter = Counter()
    for raw in raw_codes:
        for token in raw.split(","):
            try:
                symbols.add(canonical_equity("tr", token))
            except ValueError:
                rejected["invalid_kap_stock_code"] += 1
    # Reject thin/changed pages: 100 verified seed symbols remain available.
    if len(symbols) < 100:
        raise ValueError(f"KAP list unexpectedly small: {len(symbols)}; expected 100+")
    return sorted(symbols), rejected


def download_official_bist(*, timeout: float = 25.0) -> str:
    """KAP public listed-company page (no key), bounded and fail-closed."""
    req = urllib.request.Request(
        KAP_BIST_LIST_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; EBBot-Universe/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.geturl().split("/")[2].lower() != "www.kap.org.tr":
            raise ValueError("unexpected KAP redirect host")
        payload = response.read(6 * 1024 * 1024 + 1)
    if len(payload) > 6 * 1024 * 1024:
        raise ValueError("KAP listing page exceeds size limit")
    return payload.decode("utf-8", errors="strict")


def parse_xetra_equities(payload: str) -> tuple[list[str], Counter]:
    """Filter Deutsche Boerse T7 CSV to active XETR common shares (CS)."""
    rows = payload.lstrip("\ufeff").splitlines()
    index = next(
        (i for i, row in enumerate(rows[:12])
         if row.startswith("Product Status;Instrument Status;") and ";Mnemonic;" in row),
        None,
    )
    if index is None:
        raise ValueError("Xetra T7 schema missing Product Status and Mnemonic")
    reader = csv.DictReader(io.StringIO("\n".join(rows[index:])), delimiter=";")
    fields = {
        "Product Status", "Instrument Status", "Instrument Type",
        "Mnemonic", "MIC Code",
    }
    if not fields.issubset(reader.fieldnames or ()):
        raise ValueError("Xetra T7 instrument headers incomplete")
    found: set[str] = set()
    reasons: Counter = Counter()
    for item in reader:
        if (item.get("MIC Code") or "").strip().upper() != "XETR":
            reasons["non_xetra_market"] += 1
            continue
        if str(item.get("Instrument Type") or "").strip().upper() != "CS":
            reasons["non_equity_instrument"] += 1
            continue
        if (
            str(item.get("Product Status") or "").strip().lower() != "active"
            or str(item.get("Instrument Status") or "").strip().lower() != "active"
        ):
            reasons["inactive_instrument"] += 1
            continue
        try:
            found.add(canonical_equity("de", item.get("Mnemonic") or ""))
        except ValueError:
            reasons["invalid_xetra_mnemonic"] += 1
    if len(found) < 100:
        raise ValueError(f"Xetra active share list unexpectedly small: {len(found)}")
    return sorted(found), reasons


def download_official_xetra(*, timeout: float = 30.0) -> str:
    """Fetch official cash-market CSV, with bounded size and redirect host."""
    request = urllib.request.Request(
        XETRA_DIRECTORY_URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.geturl().split("/")[2].lower() != "www.cashmarket.deutsche-boerse.com":
            raise ValueError("unexpected Deutsche Boerse redirect host")
        payload = response.read(10 * 1024 * 1024 + 1)
    if len(payload) > 10 * 1024 * 1024:
        raise ValueError("Xetra T7 CSV exceeds size limit")
    return payload.decode("utf-8-sig", errors="strict")


def parse_hkex_equities(payload: bytes) -> tuple[list[str], Counter]:
    """Validate HKEX ListOfSecurities workbook, retaining Equity securities only."""
    from io import BytesIO
    import openpyxl

    if not payload.startswith(b"PK"):
        raise ValueError("HKEX workbook invalid XLSX content")
    with BytesIO(payload) as stream:
        book = openpyxl.load_workbook(stream, read_only=True, data_only=True)
        try:
            sheet = book["ListOfSecurities"]
            # The published HKEX workbook advertises an incorrect XML
            # dimension (only 8 rows) even though thousands of equity rows
            # are present. openpyxl read_only stops at that metadata unless
            # reset_dimensions() is called before streaming the sheet.
            sheet.reset_dimensions()
            head_index = None
            for i, row in enumerate(sheet.iter_rows(max_row=30, values_only=True)):
                if len(row) >= 4 and str(row[0]).strip() == "Stock Code" and str(row[2]).strip() == "Category":
                    head_index = i + 1
                    break
            if head_index is None:
                raise ValueError("HKEX workbook schema changed: Stock Code/Category headers absent")
            found: set[str] = set()
            reasons = Counter()
            for n, row in enumerate(sheet.iter_rows(min_row=head_index + 1, values_only=True), start=head_index + 1):
                if not row or not row[0]:
                    continue
                category = str(row[2] if len(row) > 2 else "").strip().lower()
                subcategory = str(row[3] if len(row) > 3 else "").strip().lower()
                if category != "equity" or not subcategory.startswith("equity securities"):
                    reasons["non_equity_instrument"] += 1
                    continue
                try:
                    symbol = _canonical_historical_hk_equity(str(row[0]))
                except ValueError:
                    reasons["invalid_hkex_code"] += 1
                    continue
                found.add(symbol)
        finally:
            book.close()
    if len(found) < 100:
        raise ValueError(f"HKEX equity directory unexpectedly small: {len(found)}")
    return sorted(found), reasons


def download_official_hkex(*, timeout: float = 30.0) -> bytes:
    """Public HKEX XLSX download, bounded, host-verified, without credentials."""
    request = urllib.request.Request(
        HKEX_DIRECTORY_URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.geturl().split("/")[2].lower() != "www.hkex.com.hk":
            raise ValueError("unexpected HKEX redirect host")
        payload = response.read(6 * 1024 * 1024 + 1)
    if len(payload) > 6 * 1024 * 1024:
        raise ValueError("HKEX listing exceeds size limit")
    return payload


def build_universe(
    seed: Path,
    additional: list[Path] | None = None,
    *,
    nasdaq_payload: str | None = None,
    bist_payload: str | None = None,
    hkex_payload: bytes | None = None,
    xetra_payload: str | None = None,
) -> tuple[dict[str, list[str]], dict]:
    """Merge verified seed with operator-supplied lists, never silently delete."""
    if hkex_payload is not None:
        raise ValueError("Hong Kong is not an active equity market")
    output = {market: [] for market in MARKETS}
    sets = {market: set() for market in MARKETS}
    origins = []
    for path in [seed, *(additional or [])]:
        loaded = parse_market_csv(path.read_text(encoding="utf-8-sig"), label=str(path))
        added = {}
        for market, symbols in loaded.items():
            new = [symbol for symbol in symbols if symbol not in sets[market]]
            output[market].extend(new)
            sets[market].update(new)
            added[market] = len(new)
        origins.append({"kind": "csv", "label": str(path), "added": added})
    if bist_payload is not None:
        listed, rejected = parse_kap_bist_page(bist_payload)
        new = [symbol for symbol in listed if symbol not in sets["tr"]]
        output["tr"].extend(new)
        sets["tr"].update(new)
        origins.append({
            "kind": "official_kap_bist_list",
            "label": KAP_BIST_LIST_URL,
            "added": {"tr": len(new)},
            "listing_eligible": len(listed),
            "listing_rejections": dict(rejected),
        })
    if xetra_payload is not None:
        listed, rejected = parse_xetra_equities(xetra_payload)
        new = [symbol for symbol in listed if symbol not in sets["de"]]
        output["de"].extend(new)
        sets["de"].update(new)
        origins.append({
            "kind": "official_xetra_t7_common_stock",
            "label": XETRA_DIRECTORY_URL,
            "added": {"de": len(new)},
            "listing_eligible": len(listed),
            "listing_rejections": dict(rejected),
        })
    if nasdaq_payload is not None:
        listed, rejected = parse_nasdaq_directory(nasdaq_payload)
        new = [symbol for symbol in listed if symbol not in sets["us"]]
        output["us"].extend(new)
        sets["us"].update(new)
        origins.append({
            "kind": "official_nasdaq_directory",
            "label": NASDAQ_DIRECTORY_URL,
            "added": {"us": len(new)},
            "listing_eligible": len(listed),
            "listing_rejections": dict(rejected),
        })
    for market in MARKETS:
        output[market].sort()
    return output, {
        "source_provenance": origins,
        "by_market": {market: len(output[market]) for market in MARKETS},
        "candidate_count": sum(map(len, output.values())),
        "confirmed_yahoo_count": 0,  # Validated by the scanner, not listing discovery.
        "all_exchange_coverage_verified": False,
    }


def write_universe(path: Path, stocks: dict[str, list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(path.name + ".tmp")
    with staged.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("market", "symbol"))
        for market in MARKETS:
            writer.writerows((market, symbol) for symbol in stocks[market])
    staged.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--additional-csv", type=Path, action="append", default=[],
                        help="Repeat for vetted BIST, Xetra or Nasdaq lists")
    parser.add_argument("--refresh-nasdaq", action="store_true",
                        help="Use official no-registration Nasdaq directory")
    parser.add_argument("--refresh-bist", action="store_true",
                        help="Use KAP's public BIST company listing")
    parser.add_argument("--refresh-xetra", action="store_true",
                        help="Use official Xetra T7 active common shares CSV")
    parser.add_argument("--output", type=Path, default=Path("data/universes/four_markets.csv"))
    parser.add_argument("--report", type=Path, default=Path("data/universes/coverage.json"))
    args = parser.parse_args()
    nasdaq = download_official_nasdaq() if args.refresh_nasdaq else None
    bist = download_official_bist() if args.refresh_bist else None
    xetra = download_official_xetra() if args.refresh_xetra else None
    stocks, report = build_universe(
        args.seed, args.additional_csv, nasdaq_payload=nasdaq,
        bist_payload=bist, xetra_payload=xetra,
    )
    if any(not stocks[m] for m in MARKETS):
        parser.error("missing market: provide at least one symbol per exchange")
    report["as_of_utc"] = datetime.now(timezone.utc).isoformat()
    report["read_only"] = True
    report["not_realtime"] = True
    write_universe(args.output, stocks)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
