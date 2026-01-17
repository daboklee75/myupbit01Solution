# MyUpbit AutoTrader 2.0

**3시간 추세 기반 동적 지정가 매매 시스템 (3-Hour Trend Based Dynamic Limit Order System)**

이 프로젝트는 업비트(Upbit) API를 활용한 자동 매매 봇입니다. 15분봉 기준 3시간의 중단기 추세를 분석하여, 상승세가 확인된 종목의 눌림목에 지정가 주문을 걸어 안정적인 수익을 추구합니다.

## ✨ 주요 특징 (Key Features)

1.  **3시간 추세 분석**: 최근 3시간(15분봉 12개)의 선형 회귀 기울기(Slope)가 양수일 때만 진입합니다.
2.  **동적 지정가 주문 (Dynamic Limit Orders)**: 시장가로 추격 매수하지 않고, 추세 강도에 따라 현재가 대비 -0.3% ~ -1.5% 낮은 가격에 지정가를 예약합니다.
3.  **지능형 청산**:
    *   **전고점 매도 예약**: 매수 체결 즉시 최근 3시간 고점에 매도 주문을 겁니다.
    *   **트레일링 스탑**: 수익이 나기 시작하면 고점 대비 0.2% 하락 시 익절합니다.
    *   **본절 보호 (Break-even)**: 수익권에 진입하면 손실을 보지 않도록 손절라인을 상향 조정합니다.
    *   **칼같은 손절**: -2.0% 도달 시 즉시 시장가 매도하여 리스크를 제한합니다.
4.  **자동 관리**: 타임아웃된 주문 취소, 쿨다운 관리, 물타기(Add-Buy) 등을 자동으로 수행합니다.

## 🚀 시작하기 (Getting Started)

### 1. 설정 (Configuration)

**Step 1: API 키 설정**
`.env` 파일을 생성하고 업비트 API 키를 입력하세요.
```ini
UPBIT_ACCESS_KEY=your_access_key
UPBIT_SECRET_KEY=your_secret_key
# ...
```

**Step 2: 봇 설정 파일 생성**
기본 템플릿을 복사하여 설정 파일을 만듭니다.
```bash
cp trader_config.example.json trader_config.json
```
이제 `trader_config.json`을 자유롭게 수정하셔도 Git 충돌이 발생하지 않습니다.

### 2. 실행 (Run)
`run.bat` 파일을 더블 클릭하거나 콘솔에서 실행하세요.
```bash
run.bat
```
*   봇과 대시보드가 동시에 실행됩니다.
*   웹 브라우저에서 `http://localhost:8501`로 접속하여 대시보드를 확인하세요.

## 📁 문서 (Documentation)
상세한 로직과 설정 방법은 `/docs` 폴더를 참고하세요.
*   [01. 진입 전략 (Trend Analysis)](docs/01_entry_strategy.md)
*   [02. 매매 로직 (Order Execution & Exit)](docs/02_automated_trading_logic.md)
*   [03. 설정 가이드 (Configuration)](docs/03_configuration_guide.md)
