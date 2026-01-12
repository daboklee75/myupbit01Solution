import pyupbit
import pandas as pd
import time
from myupbit01.universe import get_active_tickers

def get_candidates():
    """
    Fetches active tickers from the universe filtering module.
    """
    # Returns list of dicts: [{'market': 'KRW-BTC', 'korean_name': '비트코인'}, ...]
    return get_active_tickers(min_volume=50_000_000_000)

def analyze_trend(market, candle_count=100):
    """
    Fetches 1-minute candles and checks for trend alignment (SMA 5 > 20 > 60).
    
    Args:
        market (str): Ticker symbol (e.g., 'KRW-BTC')
        candle_count (int): Number of candles to fetch.
        
    Returns:
        dict or None: Analysis result if successful, None otherwise.
    """
    try:
        df = pyupbit.get_ohlcv(market, interval="minute1", count=candle_count)
        if df is None or len(df) < 60:
            return None
            
        # Calculate SMAs
        df['SMA5'] = df['close'].rolling(window=5).mean()
        df['SMA20'] = df['close'].rolling(window=20).mean()
        df['SMA60'] = df['close'].rolling(window=60).mean()
        
        # Check current trend (using the latest completed candle or current candle)
        # last = current point (t), prev = 1 min ago (t-1)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        sma5 = last['SMA5']
        sma20 = last['SMA20']
        sma60 = last['SMA60']
        price = last['close']
        
        # Check for positive arrangement (Golden Cross alignment)
        is_aligned = sma5 > sma20 > sma60
        
        # Check SMA 5 slope (Current > Previous)
        # Logic:
        # prev_ma5 = SMA5 at t-1 (Mean of t-5 ~ t-1)
        # curr_ma5 = SMA5 at t (Mean of t-4 ~ t)
        # If curr_ma5 > prev_ma5 -> Trend is rising
        curr_ma5 = last['SMA5']
        prev_ma5 = prev['SMA5']
        sma5_slope_up = curr_ma5 > prev_ma5
        
        # Calculate disparity (optional context)
        disparity_5_20 = (sma5 / sma20 - 1) * 100
        disparity_20_60 = (sma20 / sma60 - 1) * 100
        
        return {
            'market': market,
            'price': price,
            'SMA5': sma5,
            'SMA20': sma20,
            'SMA60': sma60,
            'is_aligned': is_aligned,
            'sma5_slope_up': sma5_slope_up,
            'disparity_5_20': disparity_5_20,
            'disparity_20_60': disparity_20_60
        }
        
    except Exception as e:
        print(f"Error analyzing {market}: {e}")
        return None

def scan_trends(candidates, strict_slope=True):
    """
    Scans list of candidates for uptrending coins.
    
    Args:
        candidates (list): List of candidate maps.
        strict_slope (bool): If True, requires SMA5 to be rising (current > prev).
    """
    results = []
    mode_str = "Strict (Aligned + Slope Up)" if strict_slope else "Basic (Aligned Only)"
    print(f"Scanning trends ({mode_str}) for {len(candidates)} candidates...")
    
    for coin in candidates:
        market = coin['market']
        korean_name = coin['korean_name']
        
        analysis = analyze_trend(market)
        if analysis:
            analysis['korean_name'] = korean_name
            
            # Base condition: Alignment
            if analysis['is_aligned']:
                # If strict mode, also check slope
                if strict_slope and not analysis['sma5_slope_up']:
                    continue
                results.append(analysis)
        
        # Rate limiting
        time.sleep(0.1)
        
    return results

def format_price(price):
    if price < 10:
        return f"{price:,.3f}"
    elif price < 100:
        return f"{price:,.2f}"
    else:
        return f"{price:,.0f}"

def print_results(title, coins):
    print(f"\n[{title} - Found {len(coins)} Coins]")
    if coins:
        for coin in coins:
            p_str = format_price(coin['price'])
            sma5_str = format_price(coin['SMA5'])
            sma20_str = format_price(coin['SMA20'])
            sma60_str = format_price(coin['SMA60'])
            
            print(f"- {coin['korean_name']} ({coin['market']})")
            print(f"  Price: {p_str}")
            print(f"  SMA: 5({sma5_str}) > 20({sma20_str}) > 60({sma60_str})")
            print(f"  SMA5 Slope: {'UP' if coin['sma5_slope_up'] else 'DOWN'}")
            print(f"  Disparity: 5/20({coin['disparity_5_20']:.2f}%) 20/60({coin['disparity_20_60']:.2f}%)")
            print("-" * 30)
    else:
        print("No coins found.")

if __name__ == "__main__":
    print(">>> 1. Filtering Universe (Volume > 50B KRW)...")
    candidates = get_candidates()
    print(f"Candidates found: {len(candidates)}")
    
    print("\n>>> 2. Comparing Trend Conditions...")
    
    # 1. Basic Scan (Alignment Only)
    basic_coins = scan_trends(candidates, strict_slope=False)
    
    # 2. Strict Scan (Alignment + Slope)
    strict_coins = scan_trends(candidates, strict_slope=True)
    
    print("\n" + "="*50)
    print_results("Basic (Aligned 5>20>60)", basic_coins)
    print("\n" + "="*50)
    print_results("Strict (Aligned + SMA5 Slope Up)", strict_coins)
    print("="*50)
