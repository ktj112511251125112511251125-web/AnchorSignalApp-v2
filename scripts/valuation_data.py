import csv
import io
import json
import math
import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yfinance as yf

USER_AGENT = "AnchorSignalApp/0.6.5 valuation"
HISTORY_PATH = Path(os.environ.get("VALUATION_HISTORY_PATH", "app_data/valuation_history.json"))
HOM_URLS = {
    "QQQ": "https://historyofmarket.com/api/ndx/forward-pe.json",
    "VOO": "https://historyofmarket.com/api/sp500/forward-pe.json",
}


def _finite_number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _iso_date(value):
    if value is None:
        return ""
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
        if hasattr(value, "date"):
            return value.date().isoformat()
        text = str(value).strip()
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return text[:10]
        return ""
    except Exception:
        return ""


def _request_json(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,*/*;q=0.8"}, timeout=30)
    r.raise_for_status()
    return r.json()


def yahoo_forward_pe(symbol):
    """Primary source: Yahoo Finance via yfinance."""
    ticker = yf.Ticker(symbol)
    errors = []
    info = {}
    for loader_name, loader in (("get_info", ticker.get_info), ("info", lambda: ticker.info)):
        try:
            info = loader() or {}
            pe = _finite_number(info.get("forwardPE"))
            if pe and pe > 0:
                as_of = _iso_date(info.get("regularMarketTime"))
                if not as_of:
                    hist = ticker.history(period="10d", interval="1d", auto_adjust=False, actions=False)
                    if hist is not None and not hist.empty:
                        as_of = _iso_date(hist.index[-1])
                return {"value": pe, "as_of": as_of, "source": "Yahoo Finance (yfinance)"}
        except Exception as exc:
            errors.append(f"{loader_name}: {exc}")
    raise RuntimeError("; ".join(errors) if errors else f"forwardPE field missing for {symbol}")


def _walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_dicts(value)


def _forward_series_from_hom(data):
    """Schema-tolerant parser for History of Market forward-PE JSON."""
    rows = []
    date_keys = ("date", "Date", "period", "as_of", "asOf", "timestamp")
    preferred_keys = (
        "forward_pe", "forwardPE", "forwardPe", "forward_p_e", "fwd_pe", "fwdPE",
        "forward", "forward_pe_ratio", "forwardPERatio",
    )
    for d in _walk_dicts(data):
        date = ""
        for key in date_keys:
            if key in d:
                date = _iso_date(d.get(key)) or str(d.get(key, ""))[:10]
                if len(date) == 10:
                    break
        if not date or len(date) != 10:
            continue
        pe = None
        for key in preferred_keys:
            if key in d:
                pe = _finite_number(d.get(key))
                if pe and pe > 0:
                    break
        if pe is None:
            # Last resort: key name must clearly contain both forward/fwd and pe.
            for key, value in d.items():
                low = str(key).lower().replace("-", "_")
                if (("forward" in low) or ("fwd" in low)) and ("pe" in low or "p_e" in low):
                    pe = _finite_number(value)
                    if pe and pe > 0:
                        break
        if pe and 1.0 < pe < 200.0:
            rows.append({"date": date, "value": float(pe)})
    dedup = {r["date"]: r for r in rows}
    return [dedup[k] for k in sorted(dedup)]


def index_forward_pe(symbol):
    data = _request_json(HOM_URLS[symbol])
    series = _forward_series_from_hom(data)
    if not series:
        raise RuntimeError(f"History of Market forward PE parse returned no rows for {symbol}")
    last = series[-1]
    label = "Nasdaq-100" if symbol == "QQQ" else "S&P 500"
    return {
        "value": last["value"],
        "as_of": last["date"],
        "source": f"History of Market ({label} Forward PE)",
        "series": series,
    }


def fred_series(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,*/*;q=0.8"}, timeout=30)
    r.raise_for_status()
    text = r.content.decode(r.encoding or "utf-8", errors="replace")
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        value = _finite_number(row.get(series_id))
        date = (row.get("DATE") or row.get("observation_date") or "").strip()
        if value is not None and len(date) >= 10:
            out.append({"date": date[:10], "value": value})
    if not out:
        raise RuntimeError(f"No FRED rows for {series_id}")
    return out


def fred_latest(series_id):
    row = fred_series(series_id)[-1]
    return {"value": row["value"], "as_of": row["date"], "source": "FRED"}


def yfinance_10y_latest():
    hist = yf.Ticker("^TNX").history(period="10d", interval="1d", auto_adjust=False, actions=False)
    if hist is None or hist.empty:
        raise RuntimeError("^TNX history empty")
    close = _finite_number(hist["Close"].dropna().iloc[-1])
    if close is None:
        raise RuntimeError("^TNX close missing")
    # Yahoo's ^TNX is normally quoted directly in percent (e.g. 4.2). Guard old-scaled data.
    if close > 20:
        close /= 10.0
    return {"value": close, "as_of": _iso_date(hist.index[-1]), "source": "Yahoo Finance ^TNX (yfinance)"}


def yfinance_10y_series():
    hist = yf.Ticker("^TNX").history(period="6y", interval="1d", auto_adjust=False, actions=False)
    if hist is None or hist.empty:
        return []
    out = []
    for idx, row in hist.iterrows():
        value = _finite_number(row.get("Close"))
        if value is None:
            continue
        if value > 20:
            value /= 10.0
        out.append({"date": _iso_date(idx), "value": value})
    return [r for r in out if r["date"]]


def _manual_point(name):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    value = _finite_number(raw)
    if value is None:
        return None
    as_of = os.environ.get(name + "_AS_OF", "").strip() or datetime.now(timezone.utc).date().isoformat()
    return {"value": value, "as_of": as_of, "source": "GitHub Variable"}


def _previous_point(previous, path):
    cur = previous
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    if isinstance(cur, dict) and _finite_number(cur.get("value")) is not None:
        return dict(cur)
    return None


def _choose_point(name, loaders, previous=None, errors=None):
    manual = _manual_point(name)
    if manual:
        return manual
    for label, loader in loaders:
        try:
            point = loader()
            if point and _finite_number(point.get("value")) is not None:
                return point
        except Exception as exc:
            if errors is not None:
                errors.append(f"{name}/{label}: {exc}")
            print(f"valuation warning {name}/{label}: {exc}")
    return previous


def _nearest_rate(rate_rows, date):
    if not rate_rows or not date:
        return None
    eligible = [r for r in rate_rows if r.get("date", "") <= date]
    return eligible[-1]["value"] if eligible else None


def _build_backfill(pe_series, rate_series, symbol):
    rows = []
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=365 * 5 + 45)).isoformat()
    for p in pe_series or []:
        date = p.get("date", "")
        if date < cutoff:
            continue
        pe = _finite_number(p.get("value"))
        ten = _nearest_rate(rate_series, date)
        if pe and pe > 0 and ten is not None:
            rows.append({"date": date, f"{symbol.lower()}_spread": 100.0 / pe - float(ten)})
    return rows


def _load_history():
    try:
        if HISTORY_PATH.exists():
            data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_history(rows):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_history(*groups):
    merged = {}
    for group in groups:
        for row in group or []:
            date = row.get("date", "")
            if not date:
                continue
            target = merged.setdefault(date, {"date": date})
            for key in ("qqq_spread", "voo_spread"):
                val = _finite_number(row.get(key))
                if val is not None:
                    target[key] = val
    return [merged[k] for k in sorted(merged)]


def _zscore(history, symbol, current_spread, current_date):
    if current_spread is None or not current_date:
        return None, 0, ""
    cutoff = (datetime.fromisoformat(current_date).date() - timedelta(days=365 * 5 + 2)).isoformat()
    key = f"{symbol.lower()}_spread"
    vals = []
    start = ""
    for row in history:
        if row.get("date", "") < cutoff or row.get("date", "") > current_date:
            continue
        value = _finite_number(row.get(key))
        if value is not None:
            vals.append(value)
            start = start or row.get("date", "")
    if len(vals) < 60:
        return None, len(vals), start
    sd = statistics.stdev(vals)
    if sd == 0:
        return 0.0, len(vals), start
    return (float(current_spread) - statistics.mean(vals)) / sd, len(vals), start


def _bond_signal(spread):
    if spread is None: return "UNKNOWN"
    if spread >= 1.0: return "EQUITY_ADVANTAGE"
    if spread >= 0.25: return "SLIGHT_EQUITY_ADVANTAGE"
    if spread > -0.25: return "NEUTRAL"
    if spread > -1.0: return "BOND_ADVANTAGE"
    return "STRONG_BOND_ADVANTAGE"


def _history_signal(z):
    if z is None: return "BUILDING"
    if z >= 2.0: return "VERY_ATTRACTIVE"
    if z >= 1.0: return "ATTRACTIVE"
    if z > -1.0: return "NEUTRAL"
    if z > -2.0: return "EXPENSIVE"
    return "VERY_EXPENSIVE"


def _etf_block(symbol, pe_point, us10y, history):
    if not pe_point or _finite_number(pe_point.get("value")) is None:
        return None
    pe = float(pe_point["value"])
    ey = 100.0 / pe
    ten = _finite_number(us10y.get("value")) if isinstance(us10y, dict) else None
    spread = ey - ten if ten is not None else None
    pe_date = pe_point.get("as_of", "")
    ten_date = us10y.get("as_of", "") if isinstance(us10y, dict) else ""
    as_of = max([d for d in (pe_date, ten_date) if d], default=pe_date or ten_date)
    z, count, start = _zscore(history, symbol, spread, as_of)
    return {
        "symbol": symbol,
        "forward_pe": round(pe, 4),
        "forward_pe_as_of": pe_date,
        "forward_pe_source": pe_point.get("source", ""),
        "earnings_yield": round(ey, 4),
        "earnings_yield_as_of": pe_date,
        "spread_10y": round(spread, 4) if spread is not None else None,
        "spread_as_of": as_of,
        "spread_inputs_misaligned": bool(pe_date and ten_date and pe_date != ten_date),
        "bond_signal": _bond_signal(spread),
        "zscore_5y": round(z, 4) if z is not None else None,
        "zscore_as_of": as_of,
        "zscore_observations": count,
        "zscore_history_start": start,
        "history_signal": _history_signal(z),
    }


def build_valuation(previous=None):
    previous = previous if isinstance(previous, dict) else {}
    errors = []

    # Forward PE: manual override -> Yahoo/yfinance -> index forward PE fallback -> last good.
    qqq_prev = previous.get("valuation", {}).get("qqq") if isinstance(previous.get("valuation"), dict) else None
    voo_prev = previous.get("valuation", {}).get("voo") if isinstance(previous.get("valuation"), dict) else None
    qqq_prev_point = {"value": qqq_prev.get("forward_pe"), "as_of": qqq_prev.get("forward_pe_as_of", ""), "source": qqq_prev.get("forward_pe_source", "Last good")} if isinstance(qqq_prev, dict) else None
    voo_prev_point = {"value": voo_prev.get("forward_pe"), "as_of": voo_prev.get("forward_pe_as_of", ""), "source": voo_prev.get("forward_pe_source", "Last good")} if isinstance(voo_prev, dict) else None

    qqq_index = None
    voo_index = None
    def load_qqq_index():
        nonlocal qqq_index
        qqq_index = index_forward_pe("QQQ")
        return qqq_index
    def load_voo_index():
        nonlocal voo_index
        voo_index = index_forward_pe("VOO")
        return voo_index

    qqq_pe = _choose_point("QQQ_FORWARD_PE", [("yfinance", lambda: yahoo_forward_pe("QQQ")), ("Nasdaq-100 index", load_qqq_index)], qqq_prev_point, errors)
    voo_pe = _choose_point("VOO_FORWARD_PE", [("yfinance", lambda: yahoo_forward_pe("VOO")), ("S&P 500 index", load_voo_index)], voo_prev_point, errors)

    rates_prev = previous.get("rates") if isinstance(previous.get("rates"), dict) else {}
    us10y = _choose_point("US10Y", [("FRED", lambda: fred_latest("DGS10")), ("yfinance ^TNX", yfinance_10y_latest)], rates_prev.get("us10y"), errors)
    fed_lower = _choose_point("FED_FUNDS_LOWER", [("FRED", lambda: fred_latest("DFEDTARL"))], rates_prev.get("fed_funds_lower"), errors)
    fed_upper = _choose_point("FED_FUNDS_UPPER", [("FRED", lambda: fred_latest("DFEDTARU"))], rates_prev.get("fed_funds_upper"), errors)

    # One-time historical backfill for 5Y Z-score. It prefers the same index Forward-PE
    # datasets used as fallback, paired with FRED DGS10; if FRED history is unavailable,
    # Yahoo ^TNX daily history is used instead. No synthetic PE points are invented.
    history = _load_history()
    try:
        if qqq_index is None:
            qqq_index = index_forward_pe("QQQ")
        if voo_index is None:
            voo_index = index_forward_pe("VOO")
        try:
            ten_history = fred_series("DGS10")
        except Exception as exc:
            errors.append(f"DGS10 history/FRED: {exc}")
            ten_history = yfinance_10y_series()
        back_qqq = _build_backfill(qqq_index.get("series", []), ten_history, "QQQ")
        back_voo = _build_backfill(voo_index.get("series", []), ten_history, "VOO")
        history = _merge_history(history, back_qqq, back_voo)
    except Exception as exc:
        errors.append(f"5Y backfill: {exc}")

    # Add today's/latest mixed-input observation; this preserves daily sensitivity to rates.
    pre_qqq = _etf_block("QQQ", qqq_pe, us10y, history)
    pre_voo = _etf_block("VOO", voo_pe, us10y, history)
    current_rows = []
    dates = [x.get("spread_as_of", "") for x in (pre_qqq, pre_voo) if isinstance(x, dict) and x.get("spread_as_of")]
    current_date = max(dates, default="")
    if current_date:
        row = {"date": current_date}
        if pre_qqq and _finite_number(pre_qqq.get("spread_10y")) is not None:
            row["qqq_spread"] = pre_qqq["spread_10y"]
        if pre_voo and _finite_number(pre_voo.get("spread_10y")) is not None:
            row["voo_spread"] = pre_voo["spread_10y"]
        current_rows.append(row)
    history = _merge_history(history, current_rows)
    if current_date:
        cutoff = (datetime.fromisoformat(current_date).date() - timedelta(days=365 * 5 + 45)).isoformat()
        history = [r for r in history if r.get("date", "") >= cutoff]
    try:
        _save_history(history)
    except Exception as exc:
        errors.append(f"history save: {exc}")

    qqq = _etf_block("QQQ", qqq_pe, us10y, history)
    voo = _etf_block("VOO", voo_pe, us10y, history)

    all_dates = []
    for point in (us10y, fed_lower, fed_upper):
        if isinstance(point, dict) and point.get("as_of"):
            all_dates.append(point["as_of"])
    for block in (qqq, voo):
        if isinstance(block, dict) and block.get("forward_pe_as_of"):
            all_dates.append(block["forward_pe_as_of"])

    return {
        "freshest_as_of": max(all_dates, default=""),
        "rates": {"us10y": us10y, "fed_funds_lower": fed_lower, "fed_funds_upper": fed_upper},
        "valuation": {"qqq": qqq, "voo": voo},
        "status": {
            "ok": bool(us10y and (qqq or voo)),
            "errors": errors[-12:],
            "note": "Valuation is optional; strategy merge continues even if external valuation sources fail.",
        },
    }
