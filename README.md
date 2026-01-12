# MyUpbit AutoTrader

업비트 자동매매 봇 및 웹 대시보드 프로젝트입니다.
Poetry를 사용하여 의존성을 관리합니다.

## 🚀 시작하기

### 1. 설치 (Installation)
```bash
poetry install
```

### 2. 설정 (Configuration)
1. `.env.template` 파일을 복사하여 `.env` 이름을 변경합니다.
2. `.env` 파일을 열고 업비트 API 키를 입력합니다.
   ```properties
   UPBIT_ACCESS_KEY=your_access_key
   UPBIT_SECRET_KEY=your_secret_key
   ```
   *주의: `TRADE_AMOUNT`, `MAX_SLOTS` 등의 매매 설정은 이제 `trader_config.json` 또는 웹 대시보드에서 관리합니다.*

---

## ▶️ 실행 방법 (Usage)

### 방법 1: 간편 실행 (추천)
프로젝트 폴더 내의 **`run.bat`** 파일을 더블 클릭하세요.
- 자동으로 2개의 창이 열리며 **매매 봇**과 **웹 대시보드**가 동시에 실행됩니다.

### 방법 2: 수동 실행 (터미널)
두 개의 터미널을 열고 각각 다음 명령어를 실행하세요.

**터미널 1 (매매 봇 실행):**
```bash
poetry run python src/myupbit01/main.py
```

**터미널 2 (웹 대시보드 실행):**
```bash
poetry run streamlit run src/myupbit01/app.py
```

---

## 📊 웹 대시보드 기능
- 주소: `http://localhost:8501`
- **Settings**: 투자금, 최대 슬롯, 손절/익절률 실시간 설정.
- **Scanner**: 실시간 포착된 추천 종목 및 점수 확인.
- **Status**: 보유 종목 현황 및 Panic Sell.
- **Logs**: 봇 로그 실시간 확인.
