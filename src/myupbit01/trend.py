import pyupbit
import pandas as pd
import time
import requests
from myupbit01.universe import get_active_tickers

def get_candidates():
    """
    Fetches active tickers (Top 30 by volume).
    """
    return get_active_tickers(top_n=30)

def calculate_adx(df, n=14):
    """
    Calculates ADX(14) for the given DataFrame.
    Returns the DataFrame with 'ADX' column.
    """
    try:
        # True Range
        df['tr0'] = abs(df['high'] - df['low'])
        df['tr1'] = abs(df['high'] - df['close'].shift(1))
        df['tr2'] = abs(df['low'] - df['close'].shift(1))
        df['TR'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)

        # Directional Movement
        df['up_move'] = df['high'] - df['high'].shift(1)
        df['down_move'] = df['low'].shift(1) - df['low']
        
        df['plus_dm'] = 0.0
        df.loc[(df['up_move'] > df['down_move']) & (df['up_move'] > 0), 'plus_dm'] = df['up_move']
        
        df['minus_dm'] = 0.0
        df.loc[(df['down_move'] > df['up_move']) & (df['down_move'] > 0), 'minus_dm'] = df['down_move']

        # Wilder's Smoothing
        # (Current = Prev - (Prev/n) + val)
        # Using ewm as approx for simplicity or correct wilder implementation
        alpha = 1/n
        df['TR_s'] = df['TR'].ewm(alpha=alpha, adjust=False).mean()
        df['plus_dm_s'] = df['plus_dm'].ewm(alpha=alpha, adjust=False).mean()
        df['minus_dm_s'] = df['minus_dm'].ewm(alpha=alpha, adjust=False).mean()

        df['plus_di'] = 100 * (df['plus_dm_s'] / df['TR_s'])
        df['minus_di'] = 100 * (df['minus_dm_s'] / df['TR_s'])
        
        df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
        df['ADX'] = df['dx'].ewm(alpha=alpha, adjust=False).mean()
        
        return df
    except Exception as e:
        print(f"ADX Error: {e}")
        return df

def analyze_trend(market, candle_count=200):
    try:
        # 1. Fetch 1-min candles for SMA, ADX, Volatility
        df = pyupbit.get_ohlcv(market, interval="minute1", count=candle_count)
        if df is None or len(df) < 60:
            return None
            
        # 2. Fetch 1-h candles for Volume Spike (Count=25 for 24h avg)
        df_1h = pyupbit.get_ohlcv(market, interval="minute60", count=25)
        
        # --- Indicators ---
        # SMAs
        df['SMA5'] = df['close'].rolling(window=5).mean()
        df['SMA20'] = df['close'].rolling(window=20).mean()
        df['SMA60'] = df['close'].rolling(window=60).mean()
        
        # Volatility (5-min std dev of close)
        df['std'] = df['close'].rolling(window=5).std()
        
        # ADX
        df = calculate_adx(df)
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- Metrics ---
        price = curr['close']
        
        # 1. Trend Alignment
        # Relaxed: SMA5 > SMA20 is MUST. SMA20 vs SMA60 is optional but scored.
        sma5 = curr['SMA5']
        sma20 = curr['SMA20']
        sma60 = curr['SMA60']
        is_aligned_basic = sma5 > sma20
        is_aligned_full = sma5 > sma20 > sma60
        
        # 2. SMA5 Slope
        sma5_slope_up = curr['SMA5'] > prev['SMA5']
        
        # 3. Volatility Increasing
        # Compare current std with avg of last 5 stds
        curr_std = curr['std']
        avg_std_recent = df['std'].iloc[-6:-1].mean()
        volatility_rising = curr_std > avg_std_recent
        
        # 4. ADX Check
        adx = curr['ADX']
        adx_rising = adx > prev['ADX']
        adx_strong = adx >= 25
        
        # 5. Volume Spike
        # Avg volume of previous 24h (excluding current/latest)
        vol_spike = False
        avg_vol_1h = 0
        if df_1h is not None and len(df_1h) >= 24:
            # Last 24 closed candles (excluding most recent partial?)
            # df_1h index -1 is current partial, -2 is closed. 
            # Safe logic: avg of -25 to -2 (24 candles)
            # Compare current partial (-1) or last closed (-2)
            # User wants "Recent 1h > Avg * 2". Let's use last closed (-2) for stability, or current projected.
            # Upbit provides partial volume for current candle.
            # Simple approach: usage of 'minute60' returns valid data.
            prev_24h_vols = df_1h['volume'].iloc[-25:-1] # Past 24 hours
            avg_vol_1h = prev_24h_vols.mean()
            curr_vol_1h = df_1h['volume'].iloc[-1] # Current incomplete candle volume
            
            # Scale current volume if candle is fresh? No, assume user wants raw burst.
            # But safer to compare with last CLOSED candle for definite signal, 
            # OR compare current raw if it exceeds yearly avg rapidly.
            # Let's use: Last CLOSED Candle Volume vs Avg. 
            last_closed_vol = df_1h['volume'].iloc[-2]
            if last_closed_vol > (avg_vol_1h * 2.0):
                vol_spike = True
            # Also check current just in case it's huge
            if curr_vol_1h > (avg_vol_1h * 2.5): # stricter for current
                vol_spike = True
                
        return {
            'market': market,
            'price': float(price),
            'is_aligned_basic': bool(is_aligned_basic), # SMA5 > SMA20
            'is_aligned_full': bool(is_aligned_full), # SMA5 > 20 > 60
            'sma5_slope_up': bool(sma5_slope_up),
            'volatility_rising': bool(volatility_rising),
            'adx': float(adx),
            'adx_strong': bool(adx_strong),
            'adx_rising': bool(adx_rising),
            'vol_spike': bool(vol_spike),
            'avg_vol_1h': float(avg_vol_1h)
        }
    except Exception as e:
        # print(f"Trend Error {market}: {e}")
        return None

def analyze_orderbook(market):
    try:
        # Use pyupbit.get_orderbook(ticker)
        obs = pyupbit.get_orderbook(market)
        if not obs: return 0
        
        # obs is list of dicts/or dict. pyupbit returns list[0] usually
        ob = obs[0]
        units = ob['orderbook_units']
        
        total_ask_size = sum([u['ask_size'] for u in units])
        total_bid_size = sum([u['bid_size'] for u in units])
        
        # User wants "More Sell Orders (Ask) than Buy Orders (Bid)" -> Upward pressure logic?
        # Typically: High Bid Wall = Support, High Ask Wall = Resistance.
        # User Logic: "Orderbook Imbalance: 매수 호가 잔량보다 매도 호가 잔량이 더 많은(위로 뚫으려는 힘이 강한)"
        # This usually means price tends to move up to eat the asks? or whales stacking asks to suppress?
        # In crypto momentum, usually 'Ask > Bid' is interpreted as "Resistance is heavy" but sometimes "Price moves to liquidity".
        # User explicitly requested: "Ask Size > Bid Size". We follow that.
        
        return 1 if total_ask_size > total_bid_size else 0
    except:
        return 0

def analyze_trade_strength(market):
    try:
        # Fetch recent ticks (1 min/count=50?) 
        # Pyupbit get_tick is easy
        # Need "Recent 1 min buy volume ratio".
        # ticks = pyupbit.get_transaction_history (Not get_ticks, API map needed)
        # pyupbit.get_tick(market, count=...) returns recent trades
        ticks = pyupbit.get_tick(market, count=20, verification=False)
        # Verify timestamps for 1 min? simpler: just check last 20-30 trades.
        
        total_vol = 0
        buy_vol = 0
        
        for t in ticks:
            total_vol += t['trade_volume']
            if t['ask_bid'] == 'BID': # BID = Buys (Taker Buy)
                 buy_vol += t['trade_volume']
        
        if total_vol == 0: return 0
        
        ratio = buy_vol / total_vol
        return 1 if ratio >= 0.6 else 0
    except:
        return 0

def scan_trends(candidates):
    print(f"Scanning trends for {len(candidates)} candidates...")
    
    results = []
    
    for coin in candidates:
        market = coin['market']
        korean_name = coin['korean_name']
        
        # 1. Base Trend Analysis
        trend_data = analyze_trend(market)
        if not trend_data: continue
        
        # Skip if basic alignment (5>20) failing
        if not trend_data['is_aligned_basic']:
            continue
            
        # 2. Real-time Orderbook & Trade Strength (Only if passed trend)
        ob_score = analyze_orderbook(market)
        ts_score = analyze_trade_strength(market)
        
        # 3. Scoring
        score = 0
        
        # - Aligned Full (5>20>60): +10
        if trend_data['is_aligned_full']: score += 10
        else: score += 5 # Basic aligned gives 5
        
        # - SMA5 Slope Up: +10
        if trend_data['sma5_slope_up']: score += 10
        
        # - Volatility Rising: +5
        if trend_data['volatility_rising']: score += 5
        
        # - ADX: >25(+3), Rising(+2)
        if trend_data['adx_strong']: score += 3
        if trend_data['adx_rising']: score += 2
        
        # - Volume Spike: +10 (Big Factor)
        if trend_data['vol_spike']: score += 10
        
        # - Orderbook (Ask > Bid): +5
        if ob_score: score += 5
        
        # - Trade Strength (>60% Buy): +10
        if ts_score: score += 10
        
        trend_data['score'] = score
        trend_data['korean_name'] = korean_name
        trend_data['ob_score'] = ob_score
        trend_data['ts_score'] = ts_score
        
        results.append(trend_data)
        time.sleep(0.05) # Rate limit
        
    # Sort by Score Desc
    results.sort(key=lambda x: x['score'], reverse=True)
    return results

def print_results(coins):
    print(f"\n[Scan Results - Top 5]")
    for c in coins[:5]:
        print(f"- {c['korean_name']} ({c['market']}) | Score: {c['score']}")
        print(f"  Price: {c['price']:,.0f}")
        print(f"  VolSpike: {c['vol_spike']} | VolRise: {c['volatility_rising']} | ADX: {c['adx']:.1f}")
        print(f"  FullAlign: {c['is_aligned_full']} | SlopeUp: {c['sma5_slope_up']}")
        print(f"  Ask>Bid: {bool(c['ob_score'])} | BuyStrength: {bool(c['ts_score'])}")
        print("-" * 30)

if __name__ == "__main__":
    print(">>> 1. Fetching Top 30 Active Tickers...")
    candidates = get_candidates()
    print(f"Candidates: {len(candidates)}")
    
    print(">>> 2. Scanning & Scoring...")
    results = scan_trends(candidates)
    
    print_results(results)
