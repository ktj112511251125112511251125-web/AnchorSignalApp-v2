"""기존 전략 스크립트의 마지막 부분에 붙일 때 참고하는 JSON export 예제.
실제 변수명은 현재 UPRO/DUAL 스크립트의 signal dict 구조에 맞춰 연결하면 됩니다.
"""
import json
from pathlib import Path
from datetime import datetime


def cond_rows(df, asset):
    rows = []
    if df is None:
        return rows
    sub = df[df["자산"] == asset] if "자산" in df.columns else df
    for _, r in sub.iterrows():
        rows.append({"label": str(r.get("조건", "조건")), "met": bool(r.get("충족", False))})
    return rows


def signal_to_app(sig, name, conditions):
    return {
        "symbol": str(sig.get("Asset", "")),
        "name": name,
        "price": float(sig.get("Live_Price", sig.get("Price", 0.0)) or 0.0),
        "change_pct": float(sig.get("Live_Diff_%", 0.0) or 0.0),
        "action": str(sig.get("Order_Action", "HOLD")),
        "action_kr": str(sig.get("Final_Order_Action_KR", sig.get("Order_Action", "HOLD"))),
        "live_status": str(sig.get("Live_Status_KR", "")),
        "risk_score": int(sig.get("Risk_Score", 0) or 0),
        "risk_max": 8,
        "recommended_amount": float(sig.get("Live_Order_Amount", sig.get("Recommended_Amount", 0.0)) or 0.0),
        "recommended_shares": float(sig.get("Live_Order_Shares", sig.get("Recommended_Shares", 0.0)) or 0.0),
        "current_weight": float(sig.get("Current_Weight", 0.0) or 0.0) * (100 if float(sig.get("Current_Weight", 0.0) or 0.0) <= 1 else 1),
        "target_weight": float(sig.get("Target_Weight", 0.0) or 0.0) * (100 if float(sig.get("Target_Weight", 0.0) or 0.0) <= 1 else 1),
        "reason": str(sig.get("Final_Order_Text", sig.get("Reason", ""))),
        "conditions": conditions,
    }


def save_app_json(assets, path="app_data/latest.json"):
    payload = {
        "updated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "market_label": "Anchor 전략 업데이트",
        "market_detail": "GitHub Actions에서 생성된 최신 전략 신호",
        "assets": assets,
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
