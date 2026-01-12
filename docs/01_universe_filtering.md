# 1단계: 유니버스 필터링 (Universe Filtering)

## 개요
업비트의 전 종목(약 100~200개)을 매번 분석하는 것은 비효율적이므로, 거래대금이 충분하여 유동성이 좋은 '활성 종목'을 먼저 선별합니다.

## 목표
- **대상**: 업비트 원화(KRW) 마켓
- **필터 조건**: 최근 24시간 누적 거래대금 500억 원 이상
- **예상 결과**: 약 10~20개의 종목 리스트

## 구현 상세

### 1. API 호출
- `GET /v1/market/all`: 모든 마켓 정보 조회 (KRW 마켓 필터링)
- `GET /v1/ticker`: 현재가 정보 조회 (24시간 누적 거래대금 `acc_trade_price_24h` 확인)

### 2. 로직 프름
1.  `pyupbit.get_tickers(fiat="KRW")` 또는 REST API로 KRW 마켓 티커 더미를 확보.
2.  티커 리스트를 콤마(,)로 구분하여 `/v1/ticker` API 요청 (한 번에 다수 조회 가능).
3.  응답 데이터에서 `acc_trade_price_24h` >= 50,000,000,000 (500억) 조건으로 필터링.
4.  조건을 만족하는 티커 리스트 반환.

### 3. 파일 구조
- `src/myupbit01/universe.py`: 필터링 로직 핵심 모듈

## 실행 예시
```bash
poetry run python -m src.myupbit01.universe
```
결과:
```json
['KRW-BTC', 'KRW-ETH', 'KRW-XRP', ...]
```
