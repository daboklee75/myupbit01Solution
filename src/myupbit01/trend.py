import pyupbit
import pandas as pd
import numpy as np
import time
from myupbit01.universe import get_active_tickers
from myupbit01.logger import setup_logger

logger = setup_logger("TrendEngine")

# Constants
INTERVAL = "minute15"
# 3 Hours = 12 * 15 minutes
ANALYSIS_COUNT = 12 
RSI_PERIOD = 14

def get_candidates(limit=30, min_volatility=1.0):
    """
    Fetches active tickers (Top 30 by volume).
    """
    # min_volatility in universe might be ratio (0.01) vs percentage (1.0).
    # Assuming universe uses ratio 0.01 for 1%.
    # If the user input is 1.0 (percent), we pass 0.01
    return get_active_tickers(top_n=limit, min_volatility=min_volatility/100.0)

def calculate_slope(prices):
    """
    Calculates the linear regression slope of the prices.
    Returns the slope as a percentage of the average price.
    """
    y = np.array(prices)
    if len(y) < 2: return 0.0
    
    x = np.arange(len(y))
    
    # Linear Regression: y = ax + b
    slope_val, intercept = np.polyfit(x, y, 1)
    
    avg_price = np.mean(y)
    if avg_price == 0: return 0.0
    
    # Normalize slope (Percent change per candle)
    normalized_slope = (slope_val / avg_price) * 100
    
    return normalized_slope

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def analyze_trend(market):
    try:
        # Need enough data for RSI(14) and 3H(12) window. 
        # Fetching 40 candles to be safe.
        df = pyupbit.get_ohlcv(market, interval=INTERVAL, count=40)
        
        if df is None or len(df) < (max(ANALYSIS_COUNT, RSI_PERIOD) + 2):
            return None
            
        # --- 1. RSI Calculation ---
        # Calculate RSI on the full dataframe first
        df['rsi'] = calculate_rsi(df['close'], period=RSI_PERIOD)
        
        # --- 2. 3-Hour Window Analysis ---
        # Slice the last 12 candles for trend analysis
        window_df = df.iloc[-ANALYSIS_COUNT:]
        
        # Slope
        slope = calculate_slope(window_df['close'])
        
        # Negative Slope -> Immediate Discard (No Trade)
        if slope < 0:
            return None
            
        # Channel (High/Low)
        high_3h = window_df['high'].max()
        low_3h = window_df['low'].min()
        current_price = window_df['close'].iloc[-1]
        
        # Channel Position (0.0 = Low, 1.0 = High)
        channel_range = high_3h - low_3h
        if channel_range == 0:
            channel_pos = 0.5
        else:
            channel_pos = (current_price - low_3h) / channel_range
            
        # Volume Analysis
        # Current Candle Vol vs Avg of previous 12 candles (excluding current partial)
        current_vol = window_df['volume'].iloc[-1]
        
        # We take the 12 candles BEFORE the current one for average
        prev_vol_mean = df['volume'].iloc[-(ANALYSIS_COUNT+1):-1].mean()
        
        vol_ratio = 0.0
        if prev_vol_mean > 0:
            vol_ratio = current_vol / prev_vol_mean
            
        current_rsi = df['rsi'].iloc[-1]
        
        return {
            'market': market,
            'price': float(current_price),
            'slope': slope,
            'channel_pos': channel_pos,
            'vol_ratio': vol_ratio,
            'rsi': current_rsi,
            'high_3h': float(high_3h),
            'low_3h': float(low_3h)
        }
        
    except Exception as e:
        logger.error(f"Error analyzing {market}: {e}")
        return None

def score_trend(data):
    """
    Scores the trend data based on the strategy.
    """
    score = 0
    
    # 1. Slope Score (Trend Strength)
    if data['slope'] >= 1.0:
        score += 20
    elif data['slope'] >= 0.5:
        score += 10
        
    # 2. Channel Position (Pullback)
    if data['channel_pos'] <= 0.3:
        score += 15 # Best Buy Zone (Low 30%)
    elif data['channel_pos'] <= 0.6:
        score += 5  # Stable Zone (Mid 30-60%)
        
    # 3. Volume Support
    if data['vol_ratio'] > 1.0:
        score += 5
        
    # 4. Momentum Stability (RSI)
    if 40 <= data['rsi'] <= 60:
        score += 5
        
    return score

def get_best_target(min_score=30):
    """
    Main function to get the single best target.
    """
    # 1. Fetch Candidates
    candidates = get_candidates(limit=30, min_volatility=1.0)
    logger.info(f"Scanning {len(candidates)} active tickers for 3H Trends...")
    
    scored_candidates = []
    
    for coin in candidates:
        market = coin['market']
        
        trend_data = analyze_trend(market)
        if trend_data:
            score = score_trend(trend_data)
    for coin in candidates:
        market = coin['market']
        
        trend_data = analyze_trend(market)
        if trend_data:
            score = score_trend(trend_data)
            trend_data['score'] = score
            trend_data['korean_name'] = coin['korean_name']
            
            # Store ALL scored candidates for logging, filter later
            scored_candidates.append(trend_data)
                
        # Rate limit to be nice
        time.sleep(0.05)
        
    # Sort by Score DESC, then Slope DESC
    scored_candidates.sort(key=lambda x: (x['score'], x['slope']), reverse=True)
    
    if not scored_candidates:
        logger.info("No valid trend data found for any candidate.")
        return None

    # Check top candidate against threshold
    best = scored_candidates[0]
    
    if best['score'] >= min_score:
        logger.info(f"Top Target: {best['korean_name']} ({best['market']}) Score: {best['score']} Slope: {best['slope']:.2f}%")
        # Log others for context
        for i, cand in enumerate(scored_candidates[1:3]):
             logger.info(f"Rank {i+2}: {cand['market']} (Score: {cand['score']}, Slope: {cand['slope']:.2f}%)")
        return best
    else:
        logger.info("No valid target found meeting criteria.")
        # Log the best rejected ones
        logger.info(f"Top Rejected: {best['korean_name']} ({best['market']}) Score: {best['score']} (Min: {min_score}) Slope: {best['slope']:.2f}%")
        for i, cand in enumerate(scored_candidates[1:3]):
             logger.info(f"Rank {i+2}: {cand['market']} (Score: {cand['score']}, Slope: {cand['slope']:.2f}%)")
        return None
