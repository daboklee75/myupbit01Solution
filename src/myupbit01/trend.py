import pyupbit
import pandas as pd
import time
import requests
from myupbit01.universe import get_active_tickers

def get_candidates(min_volatility=0.01):
    """
    Fetches active tickers (Top 30 by volume).
    """
    return get_active_tickers(top_n=30, min_volatility=min_volatility)

def calculate_rsi(df, period=14):
    """
    Calculates RSI(14).
    """
    try:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)

        avg_gain = gain.rolling(window=period, min_periods=1).mean()
        avg_loss = loss.rolling(window=period, min_periods=1).mean()

        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))
        return df
    except Exception as e:
        print(f"RSI Error: {e}")
        df['RSI'] = 50 # Default neutral
        return df

def calculate_adx(df, n=14):
    """
    Calculates ADX(14).
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
        # print(f"ADX Error: {e}")
        return df

def analyze_trend(market, vol_spike_ratio=3.0, rsi_threshold=70.0):
    try:
        # 1. Fetch 1-min candles (enough for SMA60/RSI/ADX)
        df = pyupbit.get_ohlcv(market, interval="minute1", count=100)
        if df is None or len(df) < 60:
            return None
            
        # 2. Fetch 5-min candles for Volume Spike (Recent 5min vs Prev 1h avg)
        # We need recent ~12+1 candles (1 hour = 12 * 5min)
        df_5m = pyupbit.get_ohlcv(market, interval="minute5", count=24)
        
        # --- Indicators ---
        # SMAs
        df['SMA5'] = df['close'].rolling(window=5).mean()
        df['SMA20'] = df['close'].rolling(window=20).mean()
        df['SMA60'] = df['close'].rolling(window=60).mean()
        
        # RSI
        df = calculate_rsi(df)
        
        # ADX
        df = calculate_adx(df)
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- Metrics & Scoring Factors ---
        price = curr['close']
        
        # A. Trend Alignment (SMA5 > SMA20) - Basic Filter
        is_aligned = curr['SMA5'] > curr['SMA20']
        
        # B. RSI (Overbought/Strong Momentum)
        rsi = curr['RSI']
        rsi_over_70 = rsi >= rsi_threshold
        
        # C. 1-Min Momentum (Price Change)
        # Compare current close vs close 1 min ago
        price_change_1m = (curr['close'] - prev['close']) / prev['close']
        is_momentum_strong = price_change_1m >= 0.015 # 1.5% in 1 min
        
        # D. Volume Spike (The most important)
        # Compare most recent 5min volume VS Avg of previous 1 hour (12 candles)
        vol_spike = False
        avg_vol_1h = 0
        current_5m_vol = 0
        if df_5m is not None and len(df_5m) >= 13:
            # -1 is current incomplete 5min candle? or just completed? 
            # Pyupbit returns historical. Last one is usually current.
            # Let's assess the LAST COMPLETED or CURRENT HUGE.
            # To be safe for "Now", we check the very last row.
            
            # Avg of previous 12 candles (1 hour)
            # iloc[-13:-1] -> 12 candles before the last one
            prev_1h_vols = df_5m['volume'].iloc[-13:-1] 
            avg_vol_1h = prev_1h_vols.mean()
            current_5m_vol = df_5m['volume'].iloc[-1]
            
            # Spike factor: 3x
            if avg_vol_1h > 0 and current_5m_vol > (avg_vol_1h * vol_spike_ratio):
                vol_spike = True
            
            # Also check if just volume is huge compared to 1 min? (handled by trade strength)
        
        # E. SMA Slope
        sma5_slope_up = curr['SMA5'] > prev['SMA5']
        
        return {
            'market': market,
            'price': float(price),
            'is_aligned': bool(is_aligned),
            'rsi': float(rsi),
            'rsi_over_70': bool(rsi_over_70),
            'price_change_1m': float(price_change_1m),
            'is_momentum_strong': bool(is_momentum_strong),
            'vol_spike': bool(vol_spike),
            'sma5_slope_up': bool(sma5_slope_up),
            'adx': float(curr['ADX']),
            'avg_vol_1h': float(avg_vol_1h),
            'current_5m_vol': float(current_5m_vol)
        }
    except Exception as e:
        # print(f"Trend Analysis Error {market}: {e}")
        return None

def analyze_orderbook(market):
    try:
        # We don't rely heavily on Ask>Bid anymore, but keep as small bonus
        obs = pyupbit.get_orderbook(market)
        if not obs: return 0
        ob = obs[0]
        units = ob['orderbook_units']
        
        total_ask = sum([u['ask_size'] for u in units])
        total_bid = sum([u['bid_size'] for u in units])
        
        # Ask > Bid means huge sell wall / resistance? 
        # OR price moves up to fill asks. 
        # Let's just track if there is significant imbalance.
        # Removing "Ask > Bid" blindly. Only used if user insisted.
        # User said "Ask size > Bid size" in prev prompt, let's keep it but low weight.
        return 1 if total_ask > total_bid else 0
    except:
        return 0

def get_recent_ticks(market, count=20):
    """
    Fetches recent trades (ticks) using Upbit API directly.
    """
    try:
        url = "https://api.upbit.com/v1/trades/ticks"
        params = {"market": market, "count": count}
        response = requests.get(url, params=params)
        return response.json()
    except Exception as e:
        # print(f"Tick Fetch Error: {e}")
        return []

def analyze_trade_strength(market, buying_power_threshold=0.55):
    try:
        # Recent 20 ticks to check Buying Power
        ticks = get_recent_ticks(market, count=20)
        if not ticks or not isinstance(ticks, list): return 0, 0.0
        
        total_vol = 0
        buy_vol = 0
        
        for t in ticks:
            v = t.get('trade_volume', 0)
            total_vol += v
            # UPBIT: ask_bid 'BID' = Buying Taker (Price up), 'ASK' = Selling Taker (Price down)
            if t.get('ask_bid') == 'BID': 
                 buy_vol += v
        
        if total_vol == 0: return 0, 0.0
        
        ratio = buy_vol / total_vol # 0.0 ~ 1.0 (0% ~ 100%)
        
        score_val = 0
        if ratio >= 0.6: score_val = 2 # Very Strong
        elif ratio >= buying_power_threshold: score_val = 1 # Strong
        
        return score_val, ratio
    except:
        return 0, 0.0

def calculate_score(t_data, ts_score_val, config=None):
    if config is None: config = {}
    # vol_spike_ratio = float(config.get("VOL_SPIKE_RATIO", 3.0)) # Used in analyze_trend, not here
    # rsi_threshold = float(config.get("RSI_THRESHOLD", 70.0)) # Used in analyze_trend
    
    score = 0
    
    # [Volume Spike] +20 (Most Important)
    if t_data['vol_spike']: score += 20
    
    # [Momentum / RSI]
    if t_data['rsi_over_70']: score += 5   # Entering Overbought (High demand)
    if t_data['is_momentum_strong']: score += 10 # 1min > 1.5% Pump
    
    # [Trade Strength] 
    if ts_score_val == 2: score += 10 # >60% Buy
    elif ts_score_val == 1: score += 5 # >55% Buy
    
    # [Trend Basics]
    if t_data['is_aligned']: score += 5
    if t_data['sma5_slope_up']: score += 5
    
    # [ADX] Bonus
    if t_data['adx'] >= 25: score += 3
    
    return score

def scan_trends(candidates, config=None):
    if config is None: config = {}
    vol_spike_ratio = float(config.get("VOL_SPIKE_RATIO", 3.0))
    rsi_threshold = float(config.get("RSI_THRESHOLD", 70.0))
    bp_threshold = float(config.get("BUYING_POWER_THRESHOLD", 0.55))
    
    print(f"Scanning trends for {len(candidates)} candidates... (Spike:{vol_spike_ratio}x, RSI:{rsi_threshold}, BP:{bp_threshold})")
    
    results = []
    
    for coin in candidates:
        market = coin['market']
        korean_name = coin['korean_name']
        
        # 1. Base Logic
        t_data = analyze_trend(market, vol_spike_ratio=vol_spike_ratio, rsi_threshold=rsi_threshold)
        if not t_data: continue
        
        # 2. Trade Strength
        ts_score_val, buy_ratio = analyze_trade_strength(market, buying_power_threshold=bp_threshold)
        
        # 3. SCORING SYSTEM (AGGRESSIVE) - Refactored
        score = calculate_score(t_data, ts_score_val, config)
        
        t_data['korean_name'] = korean_name
        t_data['score'] = score
        t_data['buy_ratio'] = buy_ratio
        
        results.append(t_data)
        time.sleep(0.05)
        
    # Sort
    results.sort(key=lambda x: x['score'], reverse=True)
    return results

def print_results(coins):
    print(f"\n[Aggressive Scan Results - Top 5]")
    for c in coins[:5]:
        print(f"- {c['korean_name']} ({c['market']}) | Score: {c['score']}")
        print(f"  Price: {c['price']:,.0f} | 1mChg: {c['price_change_1m']*100:.2f}%")
        print(f"  VolSpike: {c['vol_spike']} (Curr: {c['current_5m_vol']:.0f} vs Avg: {c['avg_vol_1h']:.0f})")
        print(f"  RSI: {c['rsi']:.1f} | BuyRatio: {c['buy_ratio']*100:.1f}%")
        print("-" * 40)

def save_scan_history(results, filename="scan_history.csv"):
    if not results: return
    
    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []
    
    for r in results:
        # Only save top candidates (e.g. score >= 10) to save space
        if r['score'] < 10: continue
        
        row = r.copy()
        row['timestamp'] = timestamp
        records.append(row)
        
    if not records: return
    
    df = pd.DataFrame(records)
    
    # Needs to handle file exist append
    import os
    if not os.path.exists(filename):
        df.to_csv(filename, index=False, encoding='utf-8-sig')
    else:
        df.to_csv(filename, mode='a', header=False, index=False, encoding='utf-8-sig')

if __name__ == "__main__":
    print(">>> 1. Fetching Top 30 Active Tickers...")
    candidates = get_candidates()
    
    print(">>> 2. Scanning & Scoring (Aggressive)...")
    results = scan_trends(candidates)
    
    print_results(results)
