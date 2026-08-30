import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from valuation_data import build_valuation
except Exception as exc:
    build_valuation = None
    print(f"valuation module unavailable: {exc}")

UPRO_URL = os.environ.get("UPRO_JSON_URL", "").strip()
DUAL_URL = os.environ.get("DUAL_JSON_URL", "").strip()
UPRO_FILE = os.environ.get("UPRO_JSON_FILE", "").strip()
DUAL_FILE = os.environ.get("DUAL_JSON_FILE", "").strip()
OUT = Path(os.environ.get("LATEST_JSON_PATH", "app_data/latest.json"))
USER_AGENT = "AnchorSignalApp-GitHubActions/0.6.5"


def read_json(url: str):
    if not url:
        raise RuntimeError("JSON URL is empty")
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def read_source(path: str, url: str):
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return read_json(url)


def safe_json(url: str):
    try:
        return read_json(url)
    except Exception as exc:
        print(f"optional data failed: {url} -> {exc}")
        return None


def moving_average(values, window):
    out = []
    total = 0.0
    q = []
    for v in values:
        q.append(v)
        total += v
        if len(q) > window:
            total -= q.pop(0)
        out.append(total / window if len(q) == window else None)
    return out


def fetch_reference_series(symbol: str):
    encoded = urllib.parse.quote(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=2y&interval=1d&events=history&includeAdjustedClose=true"
    data = safe_json(url)
    try:
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        rows = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            date = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            rows.append({"date": date, "price": float(close)})
        prices = [r["price"] for r in rows]
        ma50 = moving_average(prices, 50)
        ma200 = moving_average(prices, 200)
        for i, row in enumerate(rows):
            row["ma50"] = ma50[i]
            row["ma200"] = ma200[i]
        return rows
    except Exception as exc:
        print(f"reference series parse failed for {symbol}: {exc}")
        return []


def tail_chart(rows, value_key, ref_key=None, points=90):
    usable = []
    for r in rows:
        value = r.get(value_key)
        if not isinstance(value, (int, float)):
            continue
        item = {"date": str(r.get("date", "")), "value": float(value)}
        if ref_key:
            ref = r.get(ref_key)
            if isinstance(ref, (int, float)):
                item["reference"] = float(ref)
        usable.append(item)
    return usable[-points:]


def infer_group(label: str) -> str:
    text = label.upper()
    if any(k in label for k in ("위험", "리스크", "비상", "방어")):
        return "위험·방어"
    if any(k in label for k in ("매도", "이탈", "음전환", "하락")):
        return "매도·축소"
    if any(k in label for k in ("매수", "회복", "양전환", "눌림", "상승", "유지")):
        return "매수·보유"
    if "MACD" in text:
        return "모멘텀"
    return "기타"


def condition_summary(condition):
    current = condition.get("current_value")
    reference = condition.get("reference_value")
    if isinstance(current, (int, float)) and isinstance(reference, (int, float)):
        if reference != 0:
            gap = (float(current) / float(reference) - 1.0) * 100.0
            return f"기준 대비 {gap:+.2f}%"
        return f"기준 대비 {float(current) - float(reference):+.3f}"
    return ""


def enrich_condition(asset, condition, refs):
    label = str(condition.get("label", ""))
    upper = label.upper()
    symbol = str(asset.get("symbol", "")).upper()
    chart = asset.get("chart") if isinstance(asset.get("chart"), list) else []
    risk_score = int(asset.get("risk_score", 0) or 0)
    risk_max = int(asset.get("risk_max", 8) or 8)
    condition["group"] = condition.get("group") or infer_group(label)

    # Benchmark trend conditions. Explicit day-line labels take priority; semantic
    # "장기 추세" and "중기 추세" labels are mapped to MA200 and MA50.
    benchmark = "SPY" if "SPY" in upper else ("QQQ" if "QQQ" in upper else "")
    trend_key = None
    if benchmark:
        if "200" in label or "장기" in label:
            trend_key = "ma200"
        elif "50" in label or "중기" in label:
            trend_key = "ma50"
    if benchmark and trend_key:
        rows = refs.get(benchmark, [])
        valid = [r for r in rows if isinstance(r.get(trend_key), (int, float))]
        if valid:
            last = valid[-1]
            is_break = any(k in label for k in ("이탈", "훼손", "하락"))
            is_recovery = any(k in label for k in ("회복", "유지", "상승"))
            period_name = "200일" if trend_key == "ma200" else "50일"
            condition.update({
                "detail": f"{benchmark} 현재가와 {period_name} 이동평균선을 비교합니다. "
                          + ("현재가가 기준선 아래로 내려가면 추세 훼손으로 보고 레버리지 노출 축소를 우선합니다."
                             if is_break else "현재가가 기준선 위에 있는지 확인해 시장 추세가 유지되는지 판단합니다."),
                "reference_symbol": benchmark,
                "metric_label": f"{benchmark} 현재가",
                "current_value": last["price"],
                "reference_label": f"MA{200 if trend_key == 'ma200' else 50}",
                "reference_value": last[trend_key],
                "unit": "usd",
                "chart": tail_chart(valid, "price", trend_key),
            })
            condition["summary"] = condition_summary(condition)
            if is_recovery and not is_break:
                condition["group"] = condition.get("group") or "매수·보유"
            return condition

    # Asset price vs MA20 / MA100. Also supports labels such as "20일 이동평균 위".
    if symbol and symbol in upper and ("20" in label or "100" in label) and ("일선" in label or "이동평균" in label):
        key = "ma100" if "100" in label else "ma20"
        valid = [r for r in chart if isinstance(r.get("price"), (int, float)) and isinstance(r.get(key), (int, float))]
        if valid:
            last = valid[-1]
            period_name = "100일" if key == "ma100" else "20일"
            condition.update({
                "detail": f"{symbol} 현재가와 {period_name} 이동평균선을 비교합니다. "
                          + ("100일선은 중장기 추세 훼손 여부를 확인하는 방어 기준으로 사용합니다."
                             if key == "ma100" else "20일선은 단기 추세와 눌림 후 재진입 가능성을 확인하는 기준으로 사용합니다."),
                "reference_symbol": symbol,
                "metric_label": f"{symbol} 현재가",
                "current_value": float(last["price"]),
                "reference_label": f"MA{100 if key == 'ma100' else 20}",
                "reference_value": float(last[key]),
                "unit": "usd",
                "chart": tail_chart(valid, "price", key),
            })
            condition["summary"] = condition_summary(condition)
            return condition

    # MACD momentum conditions.
    if "MACD" in upper:
        valid = [r for r in chart if isinstance(r.get("macd_hist"), (int, float))]
        if valid:
            last = valid[-1]
            condition.update({
                "detail": "MACD Histogram을 0선과 비교해 모멘텀 방향을 확인합니다. 0선 위는 상승 모멘텀, 0선 아래는 약화 모멘텀입니다. '양전환/음전환'은 0선 통과 방향을 의미합니다.",
                "reference_symbol": symbol,
                "metric_label": "MACD Histogram",
                "current_value": float(last["macd_hist"]),
                "reference_label": "0선",
                "reference_value": 0.0,
                "unit": "",
                "chart": tail_chart(valid, "macd_hist"),
            })
            for point in condition["chart"]:
                point["reference"] = 0.0
            condition["summary"] = f"현재 {float(last['macd_hist']):+.3f}"
            return condition

    # Risk threshold condition. risk_max is used as the defensive threshold when
    # the source strategy does not provide a separate threshold.
    if "위험점수" in label or "리스크 한도" in label:
        threshold = risk_max if risk_max > 0 else 8
        condition.update({
            "detail": f"원본 전략이 계산한 현재 위험점수를 방어 기준 {threshold}점과 비교합니다. 점수가 높을수록 신규매수보다 대기·축소·방어를 우선합니다.",
            "reference_symbol": symbol,
            "metric_label": "현재 위험점수",
            "current_value": float(risk_score),
            "reference_label": "방어 기준",
            "reference_value": float(threshold),
            "unit": "점",
            "summary": f"현재 {risk_score}/{threshold}점",
            "group": "위험·방어",
        })
        return condition

    # Composite gates: explain their role without inventing a hidden formula.
    if any(k in label for k in ("매수 게이트", "매도 게이트", "눌림 조건", "비상 매도")):
        if "매수 게이트" in label:
            detail = "원본 전략의 여러 매수 필터가 동시에 충족되는지 확인하는 복합 게이트입니다. 세부 기준값은 원본 전략 JSON에 제공된 항목만 앱에서 표시합니다."
        elif "매도 게이트" in label or "비상 매도" in label:
            detail = "원본 전략의 방어·매도 조건을 묶은 복합 게이트입니다. 충족되면 비중 축소 또는 매도 판단에 사용됩니다. 앱은 원본 전략의 판정값을 그대로 표시합니다."
        else:
            detail = "추격매수를 피하고 눌림 구간에서 진입하기 위한 원본 전략의 복합 조건입니다. 정확한 내부 산식은 원본 전략 데이터가 제공하는 범위에서만 표시합니다."
        condition["detail"] = condition.get("detail") or detail
        condition["summary"] = "원본 전략 복합조건"
        return condition

    condition.setdefault("detail", "이 조건은 현재 전략의 매수·보유·매도 판단에 사용되는 필터입니다. 원본 전략의 판정값은 그대로 유지하며, 제공된 기준값이 있을 때만 수치와 그래프를 표시합니다.")
    condition.setdefault("summary", "세부 기준은 원본 전략 판정 사용")
    return condition

def enrich_asset(asset, refs):
    if not isinstance(asset, dict):
        return asset
    conditions = asset.get("conditions") if isinstance(asset.get("conditions"), list) else []
    asset["conditions"] = [enrich_condition(asset, dict(c), refs) if isinstance(c, dict) else c for c in conditions]

    score = int(asset.get("risk_score", 0) or 0)
    maximum = int(asset.get("risk_max", 8) or 8)
    asset.setdefault("risk_label", "방어 우선" if score >= maximum else ("주의" if maximum > 0 and score / maximum >= 0.5 else "정상 범위"))
    asset.setdefault("risk_detail", "위험점수는 원본 전략이 계산한 방어용 종합점수입니다. 앱에서는 현재 점수와 8점 방어 임계값을 보여주며, 원본 전략에서 세부 risk_factors를 보내면 항목별 점수도 그대로 표시합니다.")
    if not isinstance(asset.get("risk_factors"), list) or not asset.get("risk_factors"):
        asset["risk_factors"] = [{
            "label": "원본 전략 위험점수",
            "points": score,
            "max_points": maximum,
            "detail": "UPRO/QLD/TQQQ 원본 전략이 계산해 전달한 Risk_Score 값입니다. 세부 산식은 원본 전략의 risk_factors 연결 시 항목별로 확장됩니다.",
        }]
    return asset


def build_market_info(previous=None):
    info = dict(previous or {})
    fear = safe_json("https://production.dataviz.cnn.io/index/fearandgreed/graphdata")
    if isinstance(fear, dict):
        current = fear.get("fear_and_greed") or {}
        score = current.get("score")
        if isinstance(score, (int, float)):
            info["fear_greed"] = {
                "score": score,
                "rating": current.get("rating", ""),
                "previous_close": current.get("previous_close"),
                "previous_week": current.get("previous_1_week"),
                "updated_at": current.get("timestamp", ""),
                "source": "CNN Fear & Greed Index",
            }

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=50)
    query = urllib.parse.urlencode({"base": "USD", "quotes": "KRW", "from": start.isoformat(), "to": end.isoformat()})
    rates = safe_json(f"https://api.frankfurter.dev/v2/rates?{query}")
    history = []
    if isinstance(rates, list):
        for row in rates:
            if isinstance(row, dict) and row.get("base") == "USD" and row.get("quote") == "KRW" and isinstance(row.get("rate"), (int, float)):
                history.append({"date": row.get("date", ""), "rate": row["rate"]})
    direct = safe_json("https://api.frankfurter.dev/v2/rate/USD/KRW")
    if isinstance(direct, dict) and isinstance(direct.get("rate"), (int, float)):
        point = {"date": direct.get("date", end.isoformat()), "rate": direct["rate"]}
        history = [x for x in history if x.get("date") != point["date"]] + [point]
    history.sort(key=lambda x: x["date"])
    history = history[-30:]
    if history:
        latest = history[-1]["rate"]
        prev = history[-2]["rate"] if len(history) >= 2 else latest
        info["usd_krw"] = {
            "pair": "USD/KRW", "rate": latest,
            "change_pct": ((latest / prev) - 1.0) * 100.0 if prev else 0.0,
            "updated_at": history[-1]["date"], "history": history, "source": "Frankfurter",
        }
    return info or None


def main():
    previous_market = None
    previous_valuation = None
    if OUT.exists():
        try:
            previous_market = json.loads(OUT.read_text(encoding="utf-8")).get("market_info")
        except Exception:
            pass

    upro = read_source(UPRO_FILE, UPRO_URL)
    dual = read_source(DUAL_FILE, DUAL_URL)
    assets = []
    for source in (upro, dual):
        if isinstance(source, dict) and isinstance(source.get("assets"), list):
            assets.extend(source["assets"])
        elif isinstance(source, dict) and (source.get("symbol") or source.get("ticker")):
            assets.append(source)

    order = {"UPRO": 0, "QLD": 1, "TQQQ": 2}
    assets.sort(key=lambda x: order.get(str(x.get("symbol") or x.get("ticker") or "").upper(), 99))
    if not assets:
        raise RuntimeError("No assets found")

    refs = {"SPY": fetch_reference_series("SPY"), "QQQ": fetch_reference_series("QQQ")}
    assets = [enrich_asset(a, refs) for a in assets]

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "market_label": "Anchor 실제 전략 신호",
        "market_detail": "UPRO + QLD/TQQQ 자동 병합 · 전략조건 상세설명/그래프 자동 연결",
        "assets": assets,
    }
    market_info = build_market_info(previous_market)
    if market_info:
        payload["market_info"] = market_info

    # Valuation is optional by design. A temporary external-data failure must never
    # break the original Anchor strategy merge. If the new fetch fails entirely,
    # retain the last good snapshot when one exists.
    if build_valuation is not None:
        try:
            valuation_snapshot = build_valuation(previous_valuation)
            if valuation_snapshot:
                payload["valuation_snapshot"] = valuation_snapshot
            elif previous_valuation:
                payload["valuation_snapshot"] = previous_valuation
        except Exception as exc:
            print(f"valuation build failed (strategy merge continues): {exc}")
            if previous_valuation:
                payload["valuation_snapshot"] = previous_valuation

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(assets)} assets)")
    print("reference rows:", {k: len(v) for k, v in refs.items()})


if __name__ == "__main__":
    main()
