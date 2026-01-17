# 03. 설정 가이드 (Configuration)

`trader_config.json` 파일을 직접 수정하거나, 대시보드(Streamlit)의 Settings 탭에서 변경할 수 있습니다.

## 주요 설정 항목

```json
{
    "candle_interval": "minute15",      // 캔들 기준 (건드리지 마세요)
    "analysis_period_candles": 12,      // 3시간 데우터 분석 (건드리지 마세요)
    
    // 매매 기본 설정
    "TRADE_AMOUNT": 10000.0,            // 1회 매수 금액 (KRW)
    "MAX_SLOTS": 4,                     // 동시에 운영할 최대 코인 개수
    "COOLDOWN_MINUTES": 30,             // 매도 후 해당 코인 재진입 금지 시간 (분)
    
    // 진입 민감도
    "MIN_ENTRY_SCORE": 15,              // 진입에 필요한 최소 점수 (높을수록 신중)
    "RSI_THRESHOLD": 70.0,              // RSI 과매수 기준 (이보다 높으면 제외)
    "VOL_SPIKE_RATIO": 3.0,             // 거래량 급증 기준 (평균 대비 3배)
    
    // 전략 상세 파라미터 (고급)
    "slope_thresholds": {
        "strong": 2.0,                  // 강한 상승 기준 기울기
        "moderate": 0.3                 // 완만한 상승 기준 기울기
    },
    "limit_offsets": {                  // 기울기별 지정가 할인율
        "strong": 0.001,                // -0.1%
        "moderate": 0.002,              // -0.2%
        "weak": 0.005                   // -0.5%
    },
    
    // 청산 전략 (Exit Strategy)
    "exit_strategies": {
        "stop_loss": 0.05,              // 손절 기준 (5.0%)
        "stop_loss_confirm_seconds": 5, // [신규] 손절 확정 대기 시간
        "trailing_stop_trigger": 0.008, // 트레일링 스탑 발동 조건 (0.8% 수익 시)
        "trailing_stop_gap": 0.002,     // 트레일링 스탑 감지 폭
        "trailing_stop_confirm_seconds": 5, // [신규] 익절 확정 대기 시간
        "break_even_trigger": 0.007,    // 본절 보호 발동 조건
        "break_even_sl": 0.0005,        // 본절 보호 시 새로운 손절 라인
        "take_profit_target": "recent_high", // 익절 목표 기준 (최근 고점 몸통)
        "take_profit_ratio": 0.5,       // [신규] 고점 반영 비율 (0.5 = 매수가와 고점의 중간 50%)
        "add_buy_trigger": -0.03,       // [신규] 추가 매수(물타기) 발동 조건 (수익률 -3.0% 도달 시)
        "max_add_buys": 1               // [신규] 종목당 최대 추가 매수 횟수 (1회 제한)
    },
    
    "timeout_minutes": 15,              // 지정가 주문 대기 시간 (분)
    "universes_count": 30,              // 분석 대상 코인 수 (거래대금 상위 30개)
    "BUYING_POWER_THRESHOLD": 0.55      // 매수세 비율 기준 (55% 이상)
}
```

## 대시보드 설정 방법
1.  대시보드 좌측 사이드바의 **Settings** 메뉴로 이동합니다.
2.  원하는 값을 입력하거나 슬라이더로 조정합니다.
3.  **Update Config** 버튼을 누르면 즉시 `trader_config.json` 파일에 저장되며 봇에 반영됩니다.
