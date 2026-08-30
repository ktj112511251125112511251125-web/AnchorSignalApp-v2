from __future__ import annotations

import csv
import json
import math
import os
import statistics
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

USER_AGENT = "AnchorSignalApp-GitHubActions/0.4"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10,DFEDTARL,DFEDTARU"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=QQQ,VOO"
YAHOO_SUMMARY_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=summaryDetail,defaultKeyStatistics"
NY_TZ = ZoneInfo("America/New_York")


def _request_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
            "Accept": "application/json,text/csv,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _env_date(name: str) -> str | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def _latest_numeric(rows: list[dict[str, str]], key: str) -> tuple[float | None, str | None]:
    for row in reversed(rows):
        raw = (row.get(key) or "").strip()
        if not raw or raw == ".":
            continue
        try:
            return float(raw), (row.get("observation_date") or row.get("DATE") or "").strip() or None
        except ValueError:
            continue
    return None, None


def fetch_rates() -> dict[str, Any]:
    override_10y = _env_float("US10Y_OVERRIDE")
    override_lower = _env_float("FED_FUNDS_LOWER_OVERRIDE")
    override_upper = _env_float("FED_FUNDS_UPPER_OVERRIDE")
    override_10y_date = _env_date("US10Y_OVERRIDE_AS_OF")
    override_fed_date = _env_date("FED_FUNDS_OVERRIDE_AS_OF")

    rows: list[dict[str, str]] = []
    source = "FRED"
    error = None
    try:
        text = _request_text(FRED_CSV_URL)
        rows = list(csv.DictReader(text.splitlines()))
    except Exception as exc:
        error = f"FRED fetch failed: {exc}"

    us10y, us10y_date = _latest_numeric(rows, "DGS10") if rows else (None, None)
    lower, lower_date = _latest_numeric(rows, "DFEDTARL") if rows else (None, None)
    upper, upper_date = _latest_numeric(rows, "DFEDTARU") if rows else (None, None)

    today = date.today().isoformat()
    if override_10y is not None:
        us10y, us10y_date, source = override_10y, override_10y_date or today, "GitHub variable override"
    if override_lower is not None:
        lower, lower_date, source = override_lower, override_fed_date or today, "GitHub variable override"
    if override_upper is not None:
        upper, upper_date, source = override_upper, override_fed_date or today, "GitHub variable override"

    fed_dates = [d for d in (lower_date, upper_date) if d]
    fed_as_of = max(fed_dates) if fed_dates else None
    all_dates = [d for d in (us10y_date, fed_as_of) if d]
    return {
        "fed_funds_lower": lower,
        "fed_funds_upper": upper,
        "us10y": us10y,
        "fed_funds_as_of": fed_as_of,
        "us10y_as_of": us10y_date,
        "as_of": max(all_dates) if all_dates else None,
        "source": source,
        "error": error,
    }


def _raw_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    if isinstance(value, dict):
        raw = value.get("raw")
        if isinstance(raw, (int, float)) and math.isfinite(float(raw)):
            return float(raw)
    return None


def _market_date_from_epoch(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(NY_TZ).date().isoformat()
    except Exception:
        return None


def fetch_yahoo_forward_pe() -> tuple[dict[str, float], dict[str, str], str | None]:
    values: dict[str, float] = {}
    as_of: dict[str, str] = {}
    errors: list[str] = []

    try:
        payload = json.loads(_request_text(YAHOO_QUOTE_URL))
        results = payload.get("quoteResponse", {}).get("result", [])
        for item in results:
            symbol = str(item.get("symbol", "")).upper()
            if symbol not in {"QQQ", "VOO"}:
                continue
            market_date = _market_date_from_epoch(item.get("regularMarketTime"))
            if market_date:
                as_of[symbol] = market_date
            pe = _raw_number(item.get("forwardPE"))
            if pe and pe > 0:
                values[symbol] = pe
    except Exception as exc:
        errors.append(f"quote endpoint: {exc}")

    for symbol in ("QQQ", "VOO"):
        if symbol in values:
            continue
        try:
            payload = json.loads(_request_text(YAHOO_SUMMARY_URL.format(symbol=symbol)))
            result = payload.get("quoteSummary", {}).get("result") or []
            if result:
                pe = (
                    _raw_number(result[0].get("summaryDetail", {}).get("forwardPE"))
                    or _raw_number(result[0].get("defaultKeyStatistics", {}).get("forwardPE"))
                )
                if pe and pe > 0:
                    values[symbol] = pe
                    as_of.setdefault(symbol, date.today().isoformat())
        except Exception as exc:
            errors.append(f"{symbol} summary endpoint: {exc}")

    return values, as_of, "; ".join(errors) or None


def resolve_forward_pe(previous: dict[str, Any] | None = None) -> tuple[dict[str, float | None], dict[str, str], dict[str, str | None]]:
    yahoo, yahoo_dates, yahoo_error = fetch_yahoo_forward_pe()
    result: dict[str, float | None] = {}
    source: dict[str, str] = {}
    as_of: dict[str, str | None] = {}

    for symbol in ("QQQ", "VOO"):
        override = _env_float(f"{symbol}_FORWARD_PE")
        override_date = _env_date(f"{symbol}_FORWARD_PE_AS_OF")
        if override is not None and override > 0:
            result[symbol] = override
            source[symbol] = "GitHub variable override"
            as_of[symbol] = override_date or date.today().isoformat()
            continue
        if symbol in yahoo:
            result[symbol] = yahoo[symbol]
            source[symbol] = "Yahoo Finance"
            as_of[symbol] = yahoo_dates.get(symbol) or date.today().isoformat()
            continue

        old_value = None
        old_date = None
        if previous:
            old_item = previous.get("valuation", {}).get(symbol.lower(), {})
            old_value = old_item.get("forward_pe")
            old_date = old_item.get("forward_pe_as_of")
        if isinstance(old_value, (int, float)) and old_value > 0:
            result[symbol] = float(old_value)
            source[symbol] = "Previous latest.json fallback"
            as_of[symbol] = str(old_date) if old_date else None
        else:
            result[symbol] = None
            source[symbol] = "Unavailable"
            as_of[symbol] = None

    if yahoo_error:
        source["yahoo_error"] = yahoo_error
    return result, source, as_of


def _finite_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        value = float(value)
        return value if math.isfinite(value) else None
    return None


def load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
    except Exception:
        pass
    return []


def update_history(path: Path, observed_date: str, us10y: float | None, spreads: dict[str, float | None]) -> list[dict[str, Any]]:
    history = load_history(path)
    row = {
        "date": observed_date,
        "us10y": us10y,
        "qqq_spread": spreads.get("QQQ"),
        "voo_spread": spreads.get("VOO"),
    }
    history = [item for item in history if item.get("date") != observed_date]
    history.append(row)
    history.sort(key=lambda item: str(item.get("date", "")))

    cutoff = date.fromisoformat(observed_date) - timedelta(days=5 * 366 + 7)
    trimmed: list[dict[str, Any]] = []
    for item in history:
        try:
            d = date.fromisoformat(str(item.get("date")))
        except Exception:
            continue
        if d >= cutoff:
            trimmed.append(item)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")
    return trimmed


def compute_zscore(history: list[dict[str, Any]], symbol: str, current_spread: float | None) -> dict[str, Any]:
    key = f"{symbol.lower()}_spread"
    values = [_finite_number(row.get(key)) for row in history]
    values = [v for v in values if v is not None]
    if current_spread is None or len(values) < 20:
        return {
            "zscore_5y": None,
            "history_points": len(values),
            "history_ready": False,
            "history_signal": "데이터 축적중",
        }
    mean = statistics.fmean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    z = 0.0 if std <= 1e-12 else (current_spread - mean) / std
    return {
        "zscore_5y": round(z, 3),
        "history_points": len(values),
        "history_ready": True,
        "spread_5y_mean": round(mean, 3),
        "spread_5y_std": round(std, 3),
        "history_signal": history_signal(z),
    }


def bond_signal(spread: float | None) -> str:
    if spread is None:
        return "데이터 없음"
    if spread >= 1.0:
        return "주식 우위"
    if spread >= 0.25:
        return "약한 주식 우위"
    if spread > -0.25:
        return "중립"
    if spread > -1.0:
        return "채권 우위"
    return "강한 채권 우위"


def history_signal(z: float | None) -> str:
    if z is None:
        return "데이터 축적중"
    if z >= 2.0:
        return "매우 매력적"
    if z >= 1.0:
        return "매력적"
    if z > -1.0:
        return "중립"
    if z > -2.0:
        return "부담"
    return "매우 부담"


def build_valuation(previous: dict[str, Any] | None, history_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    rates = fetch_rates()
    forward_pe, pe_sources, pe_dates = resolve_forward_pe(previous)
    us10y = _finite_number(rates.get("us10y"))
    us10y_as_of = rates.get("us10y_as_of")

    spreads: dict[str, float | None] = {}
    items: dict[str, Any] = {}
    for symbol in ("QQQ", "VOO"):
        pe = _finite_number(forward_pe.get(symbol))
        earnings_yield = (100.0 / pe) if pe and pe > 0 else None
        spread = (earnings_yield - us10y) if earnings_yield is not None and us10y is not None else None
        spreads[symbol] = spread
        source_dates = [d for d in (pe_dates.get(symbol), us10y_as_of) if d]
        spread_as_of = max(source_dates) if source_dates else None
        items[symbol.lower()] = {
            "forward_pe": round(pe, 3) if pe is not None else None,
            "forward_pe_as_of": pe_dates.get(symbol),
            "earnings_yield": round(earnings_yield, 3) if earnings_yield is not None else None,
            "earnings_yield_as_of": pe_dates.get(symbol),
            "spread_vs_10y": round(spread, 3) if spread is not None else None,
            "spread_as_of": spread_as_of,
            "bond_signal": bond_signal(spread),
            "forward_pe_source": pe_sources.get(symbol, "Unavailable"),
        }

    candidate_dates = [rates.get("as_of"), pe_dates.get("QQQ"), pe_dates.get("VOO")]
    observed_date = max([d for d in candidate_dates if d], default=datetime.now(timezone.utc).date().isoformat())
    history = update_history(history_path, observed_date, us10y, spreads)
    for symbol in ("QQQ", "VOO"):
        items[symbol.lower()].update(compute_zscore(history, symbol, spreads[symbol]))
        items[symbol.lower()]["zscore_as_of"] = observed_date

    rates_payload = {
        "fed_funds_lower": _finite_number(rates.get("fed_funds_lower")),
        "fed_funds_upper": _finite_number(rates.get("fed_funds_upper")),
        "fed_funds_as_of": rates.get("fed_funds_as_of"),
        "us10y": us10y,
        "us10y_as_of": us10y_as_of,
        "as_of": rates.get("as_of") or observed_date,
        "source": rates.get("source", "FRED"),
    }
    if rates.get("error"):
        rates_payload["warning"] = rates["error"]
    if pe_sources.get("yahoo_error"):
        rates_payload["valuation_warning"] = pe_sources["yahoo_error"]

    return rates_payload, items
