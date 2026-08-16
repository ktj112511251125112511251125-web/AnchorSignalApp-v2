# Anchor Signal App — Android / Kotlin / Jetpack Compose

기존 UPRO + QLD/TQQQ Python 전략 결과를 휴대폰에서 보기 위한 개인용 Android 앱 1차 버전입니다.

## 현재 구현
- Kotlin + Jetpack Compose + Material 3 다크 UI
- UPRO / QLD / TQQQ 카드
- BUY / HOLD / WAIT / SELL 상태 색상
- 현재가, 등락률, 현재/목표 비중
- 위험점수 게이지
- 상세 화면: 추천 주문, 전략 사유, 조건 충족 여부
- 새로고침
- `latest.json` 원격 연결 준비
- 원격 URL을 설정하지 않으면 내장 샘플 데이터로 즉시 실행

## Android Studio에서 실행
1. Android Studio 최신 버전 설치
2. 이 폴더 `AnchorSignalApp`을 Open
3. Gradle Sync
4. Android 폰에서 개발자 옵션 → USB 디버깅 활성화 후 연결
5. Run 버튼

## 실제 GitHub 데이터 연결
`app/src/main/java/com/anchor/signalapp/data/AppConfig.kt`의 값을 변경합니다.

```kotlin
const val REMOTE_JSON_URL = "https://raw.githubusercontent.com/USER/REPO/main/app_data/latest.json"
```

앱은 아래 JSON 규격을 기대합니다. 현재 `app/src/main/assets/sample_signal.json`을 그대로 템플릿으로 사용하면 됩니다.

## 다음 단계
1. UPRO Python에서 `latest.json`용 데이터 export
2. QLD/TQQQ Python에서 같은 JSON에 데이터 병합
3. GitHub Actions 실행 후 `app_data/latest.json` 갱신
4. Android 앱의 REMOTE_JSON_URL 연결
5. 필요하면 보유수량/평균단가 입력 화면, 차트, 알림 추가

> 이 앱은 전략 신호를 표시하는 개인용 도구입니다. 실제 주문은 앱이 자동 실행하지 않습니다.
