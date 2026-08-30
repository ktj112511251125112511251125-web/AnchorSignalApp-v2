import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

from valuation_data import build_valuation

UPRO_URL = os.environ.get("UPRO_JSON_URL", "").strip()
DUAL_URL = os.environ.get("DUAL_JSON_URL", "").strip()
OUT = Path(os.environ.get("LATEST_JSON_PATH", "app_data/latest.json"))
HISTORY = Path(os.environ.get("VALUATION_HISTORY_PATH", "app_data/valuation_history.json"))


def read_json(source: str):
    if not source:
        raise RuntimeError("JSON source is empty")
    local = Path(source)
    if local.exists():
        return json.loads(local.read_text(encoding="utf-8"))
    req = urllib.request.Request(source, headers={"Cache-Control": "no-cache", "User-Agent": "AnchorSignalApp-GitHubActions"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def read_previous():
    if not OUT.exists():
        return None
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    upro = read_json(UPRO_URL)
    dual = read_json(DUAL_URL)
    assets = []
    assets.extend(upro.get("assets", []))
    assets.extend(dual.get("assets", []))
    order = {"UPRO": 0, "QLD": 1, "TQQQ": 2}
    assets.sort(key=lambda x: order.get(str(x.get("symbol", "")).upper(), 99))
    if not assets:
        raise RuntimeError("No assets found")

    previous = read_previous()
    rates, valuation = build_valuation(previous, HISTORY)

    payload = {
        "updated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "market_label": "Anchor 실제 전략 신호",
        "market_detail": "UPRO + QLD/TQQQ + QQQ/VOO 밸류에이션 자동 병합",
        "rates": rates,
        "valuation": valuation,
        "assets": assets,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(assets)} assets)")
    print("valuation:", json.dumps(valuation, ensure_ascii=False))


if __name__ == "__main__":
    main()
