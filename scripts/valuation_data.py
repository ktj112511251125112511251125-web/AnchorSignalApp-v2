import csv
import io
import json
import math
import os
import statistics
import requests
import yfinance as yf
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER_AGENT = "Mozilla/5.0 AnchorSignalApp/0.6.5"
HISTORY_PATH = Path(os.environ.get("VALUATION_HISTORY_PATH", "app_data/valuation_history.json"))


def _iso_date(value):
    """Convert common yfinance timestamps/date-like values to YYYY-MM-DD."""
    if value is None:
        return ""
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
        if hasattr(value, "date"):
            return value.date().isoformat()
        text = str(value).strip()
        return text[:10] if len(text) >= 10 else text
    except Exception:
        return ""


def yahoo_forward_pe(symbol: str):
    """Fetch ETF forward P/E through yfinance.

    yfinance manages Yahoo's cookie/crumb flow, which is substantially more reliable
    on GitHub Actions than calling Yahoo's quote/quoteSummary endpoints directly.
    Yahoo does not expose a dedicated valuation calculation date, so the accompanying
    as_of date is the latest available market session for the symbol.
    """
    ticker = yf.Ticker(symbol)
    errors = []

    pe = None
    info = {}
    try:
        info = ticker.get_info() or {}
        candidate = info.get("forwardPE")
        if isinstance(candidate, (int, float)) and math.isfinite(float(candidate)) and float(candidate) > 0:
            pe = float(candidate)
    except Exception as exc:
        errors.append(f"get_info: {exc}")

    # Some yfinance/Yahoo combinations expose the field through .info even when
    # get_info() is incomplete. Keep this as a second best-effort path.
    if pe is None:
        try:
            info2 = ticker.info or {}
            candidate = info2.get("forwardPE")
            if isinstance(candidate, (int, float)) and math.isfinite(float(candidate)) and float(candidate) > 0:
                pe = float(candidate)
                if not info:
                    info = info2
        except Exception as exc:
            errors.append(f"info: {exc}")

    if pe is None:
        raise RuntimeError(f"yfinance forward P/E unavailable for {symbol}: {' | '.join(errors) or 'field missing'}")

    as_of = _iso_date(info.get("regularMarketTime"))
    if not as_of:
        try:
            hist = ticker.history(period="10d", interval="1d", auto_adjust=False, actions=False)
            if hist is not None and not hist.empty:
                as_of = _iso_date(hist.index[-1])
        except Exception as exc:
            errors.append(f"history date: {exc}")

    return {
        "value": pe,
        "as_of": as_of,
        "source": "Yahoo Finance (yfinance)",
    }


def fred_latest(series_id: str):
    """Latest non-missing observation from the official FRED CSV endpoint."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv,*/*;q=0.8"},
        timeout=25,
    )
    response.raise_for_status()
    # requests transparently handles gzip/brotli transfer encoding. FRED CSV itself
    # is UTF-8/ASCII, so response.text avoids the raw compressed-byte decode bug.
    text = response.text
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise RuntimeError(f"Empty FRED response for {series_id}")

    for row in reversed(rows):
        value = (row.get(series_id) or "").strip()
        if value and value != ".":
            date_value = (row.get("DATE") or row.get("observation_date") or "").strip()
            return {"value": float(value), "as_of": date_value, "source": "FRED"}
    raise RuntimeError(f"No FRED data for {series_id}")


def _manual_or_live(env_name, loader, previous=None):
    manual = os.environ.get(env_name, "").strip()
    if manual:
        try:
            value = float(manual)
            date = os.environ.get(env_name + "_AS_OF", "").strip() or datetime.now(timezone.utc).date().isoformat()
            return {"value": value, "as_of": date, "source": "GitHub Variable"}
        except ValueError:
            pass
    try:
        return loader()
    except Exception as exc:
        print(f"valuation warning: {env_name}: {exc}")
        if isinstance(previous, dict) and isinstance(previous.get("value"), (int, float)):
            return dict(previous)
        return None


def _load_history():
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_history(rows):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _signal_from_spread(spread):
    if spread is None:
        return "UNKNOWN"
    if spread >= 1.0:
        return "EQUITY_ADVANTAGE"
    if spread >= 0.25:
        return "SLIGHT_EQUITY_ADVANTAGE"
    if spread > -0.25:
        return "NEUTRAL"
    if spread > -1.0:
        return "BOND_ADVANTAGE"
    return "STRONG_BOND_ADVANTAGE"


def _history_signal(z):
    if z is None:
        return "BUILDING"
    if z >= 2.0:
        return "VERY_ATTRACTIVE"
    if z >= 1.0:
        return "ATTRACTIVE"
    if z > -1.0:
        return "NEUTRAL"
    if z > -2.0:
        return "EXPENSIVE"
    return "VERY_EXPENSIVE"


def _zscore(rows, symbol, current_spread, current_date):
    if current_spread is None or not current_date:
        return None, 0, ""
    cutoff = (datetime.fromisoformat(current_date).date() - timedelta(days=365 * 5 + 2)).isoformat()
    vals = []
    start = ""
    for row in rows:
        if row.get("date", "") < cutoff:
            continue
        v = row.get(f"{symbol.lower()}_spread")
        if isinstance(v, (int, float)) and math.isfinite(float(v)):
            vals.append(float(v))
            if not start:
                start = row.get("date", "")
    # Do not call a very short history a 5Y Z-score. Keep accumulating until there
    # are enough observations to be useful; the UI will explicitly show BUILDING.
    if len(vals) < 60:
        return None, len(vals), start
    sd = statistics.stdev(vals)
    if sd == 0:
        return 0.0, len(vals), start
    return (float(current_spread) - statistics.mean(vals)) / sd, len(vals), start


def _etf_block(symbol, pe_point, us10y, history):
    if not pe_point:
        return None
    pe = float(pe_point["value"])
    earnings_yield = 100.0 / pe if pe > 0 else None
    ten = us10y.get("value") if us10y else None
    spread = earnings_yield - float(ten) if earnings_yield is not None and isinstance(ten, (int, float)) else None
    pe_date = pe_point.get("as_of", "")
    ten_date = us10y.get("as_of", "") if us10y else ""
    derived_date = max([d for d in (pe_date, ten_date) if d], default="")
    mixed = bool(pe_date and ten_date and pe_date != ten_date)
    z, count, history_start = _zscore(history, symbol, spread, derived_date)
    return {
        "symbol": symbol,
        "forward_pe": round(pe, 4),
        "forward_pe_as_of": pe_date,
        "forward_pe_source": pe_point.get("source", ""),
        "earnings_yield": round(earnings_yield, 4) if earnings_yield is not None else None,
        "earnings_yield_as_of": pe_date,
        "spread_10y": round(spread, 4) if spread is not None else None,
        "spread_as_of": derived_date,
        "spread_inputs_misaligned": mixed,
        "bond_signal": _signal_from_spread(spread),
        "zscore_5y": round(z, 4) if z is not None else None,
        "zscore_as_of": derived_date,
        "zscore_observations": count,
        "zscore_history_start": history_start,
        "history_signal": _history_signal(z),
    }


def build_valuation(previous=None):
    previous = previous if isinstance(previous, dict) else {}
    prev_rates = previous.get("rates") if isinstance(previous.get("rates"), dict) else {}
    prev_valuation = previous.get("valuation") if isinstance(previous.get("valuation"), dict) else {}

    qqq_prev = prev_valuation.get("qqq") if isinstance(prev_valuation.get("qqq"), dict) else {}
    voo_prev = prev_valuation.get("voo") if isinstance(prev_valuation.get("voo"), dict) else {}

    qqq_pe = _manual_or_live(
        "QQQ_FORWARD_PE",
        lambda: yahoo_forward_pe("QQQ"),
        {"value": qqq_prev.get("forward_pe"), "as_of": qqq_prev.get("forward_pe_as_of", ""), "source": qqq_prev.get("forward_pe_source", "Last good value")},
    )
    voo_pe = _manual_or_live(
        "VOO_FORWARD_PE",
        lambda: yahoo_forward_pe("VOO"),
        {"value": voo_prev.get("forward_pe"), "as_of": voo_prev.get("forward_pe_as_of", ""), "source": voo_prev.get("forward_pe_source", "Last good value")},
    )

    us10y = _manual_or_live("US10Y", lambda: fred_latest("DGS10"), prev_rates.get("us10y"))
    fed_lower = _manual_or_live("FED_FUNDS_LOWER", lambda: fred_latest("DFEDTARL"), prev_rates.get("fed_funds_lower"))
    fed_upper = _manual_or_live("FED_FUNDS_UPPER", lambda: fred_latest("DFEDTARU"), prev_rates.get("fed_funds_upper"))

    history = _load_history()
    qqq = _etf_block("QQQ", qqq_pe, us10y, history)
    voo = _etf_block("VOO", voo_pe, us10y, history)

    # Append/update one row for the latest derived date. This is tiny (~one JSON row/day)
    # and only retains five calendar years plus a small buffer.
    dates = [x.get("spread_as_of", "") for x in (qqq, voo) if isinstance(x, dict) and x.get("spread_as_of")]
    history_date = max(dates, default="")
    if history_date:
        new_row = {"date": history_date}
        if qqq and isinstance(qqq.get("spread_10y"), (int, float)):
            new_row["qqq_spread"] = qqq["spread_10y"]
        if voo and isinstance(voo.get("spread_10y"), (int, float)):
            new_row["voo_spread"] = voo["spread_10y"]
        history = [r for r in history if r.get("date") != history_date] + [new_row]
        history.sort(key=lambda r: r.get("date", ""))
        cutoff = (datetime.fromisoformat(history_date).date() - timedelta(days=365 * 5 + 35)).isoformat()
        history = [r for r in history if r.get("date", "") >= cutoff]
        _save_history(history)
        # Recalculate Z-score including today's point.
        qqq = _etf_block("QQQ", qqq_pe, us10y, history)
        voo = _etf_block("VOO", voo_pe, us10y, history)

    all_dates = []
    for point in (us10y, fed_lower, fed_upper):
        if isinstance(point, dict) and point.get("as_of"):
            all_dates.append(point["as_of"])
    for item in (qqq, voo):
        if isinstance(item, dict) and item.get("forward_pe_as_of"):
            all_dates.append(item["forward_pe_as_of"])
    freshest = max(all_dates, default="")

    return {
        "freshest_as_of": freshest,
        "rates": {
            "us10y": us10y,
            "fed_funds_lower": fed_lower,
            "fed_funds_upper": fed_upper,
        },
        "valuation": {"qqq": qqq, "voo": voo},
    }
