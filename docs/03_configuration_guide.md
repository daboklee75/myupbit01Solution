# 03. 설정 가이드 (Configuration)

`trader_config.json` 파일을 직접 수정하거나, 대시보드(Streamlit)의 Settings 탭에서 변경할 수 있습니다.

## 주요 설정 항목

```json
{
    "candle_interval": "minute15",      // 캔들 기준 (건드리지 마세요)
    "analysis_period_candles": 12,      // 3시간 데우터 분석 (건드리지 마세요)
    
    // 매매 기본 설정
    "TRADE_AMOUNT": 10000,              // 1회 매수 금액 (KRW)
    "MAX_SLOTS": 3,                     // 동시에 운영할 최대 코인 개수
    "COOLDOWN_MINUTES": 30,             // 매도 후 해당 코인 재진입 금지 시간 (분)
    
    // 진입 민감도
    "min_entry_score": 30,              // 진입에 필요한 최소 점수 (높을수록 신중)
    
    // 전략 상세 파라미터 (고급)
    "slope_thresholds": {
        "strong": 2.0,                  // 강한 상승 기준 기울기
        "moderate": 0.5                 // 완만한 상승 기준 기울기
    },
    "limit_offsets": {                  // 기울기별 지정가 할인율
        "strong": 0.003,                // -0.3%
        "moderate": 0.010,              // -1.0%
        "weak": 0.015                   // -1.5%
    },
    
    // 청산 전략 (Exit Strategy)
    "exit_strategies": {
        "stop_loss": 0.02,              // 손절 기준 (2.0%)
        "trailing_stop_trigger": 0.005, // 트레일링 스탑 발동 조건 (0.5% 수익 시)
        "trailing_stop_gap": 0.002,     // 트레일링 스탑 감지 폭 (0.2% 하락 시)
        "break_even_trigger": 0.007,    // 본절 보호 발동 조건 (0.7% 수익 시)
        "break_even_sl": 0.0005         // 본절 보호 시 새로운 손절 라인 (+0.05%)
    },
    
    "timeout_minutes": 15               // 지정가 주문 대기 시간 (분)
}
```

## 대시보드 설정 방법
1.  대시보드 좌측 사이드바의 **Settings** 메뉴로 이동합니다.
2.  원하는 값을 입력하거나 슬라이더로 조정합니다.
3.  **Update Config** 버튼을 누르면 즉시 `trader_config.json` 파일에 저장되며 봇에 반영됩니다.
