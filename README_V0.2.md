# AnchorSignalApp v0.2

v0.1의 샘플 카드 앱을 실제 UPRO / QLD / TQQQ 전략 JSON과 연결하기 위한 버전입니다.

## 데이터 흐름
1. UPRO repo: 전략 실행 후 `app_data/upro_latest.json` 생성 및 커밋
2. DUAL repo: 전략 실행 후 `app_data/dual_latest.json` 생성 및 커밋
3. AnchorSignalApp repo: GitHub Actions가 두 raw JSON을 읽어 `app_data/latest.json`으로 병합
4. Android 앱: `AppConfig.REMOTE_JSON_URL` 하나만 읽음

## GitHub Repository Variables
AnchorSignalApp repo > Settings > Secrets and variables > Actions > Variables 에 다음 두 값을 등록합니다.

- `UPRO_JSON_URL`: UPRO repo의 raw `app_data/upro_latest.json` URL
- `DUAL_JSON_URL`: DUAL repo의 raw `app_data/dual_latest.json` URL

## Android 연결
`app/src/main/java/com/anchor/signalapp/data/AppConfig.kt`에서 `REMOTE_JSON_URL`을 AnchorSignalApp repo의 raw `app_data/latest.json` 주소로 지정합니다.

## v0.2 화면 데이터
- UPRO / QLD / TQQQ 실제 전략 행동
- 실시간 추천 금액 / 추천 수량
- 현재 보유수량 / 평균단가 / 평가금액
- 현재비중 / 목표비중
- 위험점수
- BUY / SELL Ready
- 조건 충족 여부
- 최근 180 거래일 가격 / MA20 / MA100 / RSI14 / MACD Histogram
- 최신 전략 BUY/SELL marker

현재 marker는 해당 실행 시점의 실제 전략 action을 마지막 데이터 포인트에 표시합니다. 장기간의 과거 BUY/SELL 체결점까지 표시하려면 trade log를 GitHub에 지속 저장한 뒤 marker 배열에 합치는 방식으로 확장하면 됩니다.
