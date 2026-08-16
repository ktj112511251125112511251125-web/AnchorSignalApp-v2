import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

UPRO_URL = os.environ.get("UPRO_JSON_URL", "").strip()
DUAL_URL = os.environ.get("DUAL_JSON_URL", "").strip()
OUT = Path(os.environ.get("LATEST_JSON_PATH", "app_data/latest.json"))


def read_json(url: str):
    if not url:
        raise RuntimeError("JSON URL is empty")
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "AnchorSignalApp-GitHubActions"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    upro = read_json(UPRO_URL)
    dual = read_json(DUAL_URL)
    assets = []
    assets.extend(upro.get("assets", []))
    assets.extend(dual.get("assets", []))
    order = {"UPRO": 0, "QLD": 1, "TQQQ": 2}
    assets.sort(key=lambda x: order.get(str(x.get("symbol", "")), 99))
    if not assets:
        raise RuntimeError("No assets found")
    payload = {
        "updated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "market_label": "Anchor 실제 전략 신호",
        "market_detail": "UPRO + QLD/TQQQ GitHub Actions 결과를 자동 병합한 latest.json",
        "assets": assets,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(assets)} assets)")


if __name__ == "__main__":
    main()
