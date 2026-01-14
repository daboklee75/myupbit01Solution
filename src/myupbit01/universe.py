import pyupbit
import requests
import time

def get_market_names():
    """
    Fetches all market information to map tickers to their Korean names.
    Returns:
        dict: A dictionary mapping 'KRW-BTC' -> '비트코인'
    """
    url = "https://api.upbit.com/v1/market/all"
    try:
        response = requests.get(url, params={"isDetails": "false"})
        response.raise_for_status()
        data = response.json()
        market_map = {}
        for item in data:
            if item['market'].startswith('KRW-'):
                market_map[item['market']] = item['korean_name']
        return market_map
    except Exception as e:
        print(f"Error fetching market names: {e}")
        return {}

def get_krw_tickers():
    """
    Fetches all KRW market tickers from Upbit.
    Returns:
        list: A list of ticker strings (e.g., ['KRW-BTC', 'KRW-ETH'])
    """
    try:
        tickers = pyupbit.get_tickers(fiat="KRW")
        return tickers
    except Exception as e:
        print(f"Error fetching tickers: {e}")
        return []

def get_active_tickers(top_n=30, min_volatility=0.01):
    """
    Returns top N tickers based on 24-hour accumulated trading volume.
    
    Args:
        top_n (int): Number of top tickers to return (default: 30).
        min_volatility (float): Minimum absolute change rate (default: 0.01 = 1%).
        
    Returns:
        list: A list of dicts [{'market': 'KRW-BTC', 'korean_name': '비트코인', 'volume': 10000000}, ...]
    """
    tickers = get_krw_tickers()
    if not tickers:
        return []
    
    # Pre-fetch market names
    name_map = get_market_names()

    url = "https://api.upbit.com/v1/ticker"
    all_ticker_data = []
    
    chunk_size = 50
    
    for i in range(0, len(tickers), chunk_size):
        batch_tickers = tickers[i:i + chunk_size]
        markets = ",".join(batch_tickers)
        params = {"markets": markets}
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            all_ticker_data.extend(data)
            time.sleep(0.1) 
        except Exception as e:
            print(f"Error fetching ticker details for batch {i}: {e}")
            
    # Sort by 24h trading volume (descending)
    all_ticker_data.sort(key=lambda x: x['acc_trade_price_24h'], reverse=True)
    
    # [MODIFIED] Filter out stablecoins and low volatility coins
    EXCLUDE_TICKERS = ['KRW-USDT', 'KRW-XAUT', 'KRW-USDC']

    top_tickers = []
    count = 0
    
    for item in all_ticker_data:
        market = item['market']
        
        # 1. Blacklist check
        if market in EXCLUDE_TICKERS:
            continue
            
        # 2. Volatility check (Must move at least 1%)
        # signed_change_rate is e.g. 0.05 for 5%
        if abs(item['signed_change_rate']) < min_volatility:
            continue

        top_tickers.append({
            'market': market,
            'korean_name': name_map.get(market, market),
            'volume': item['acc_trade_price_24h']
        })
        
        count += 1
        if count >= top_n:
            break
            
    return top_tickers

if __name__ == "__main__":
    print("Fetching active tickers (Volume >= 50 Billion KRW)...")
    active_coins = get_active_tickers()
    print(f"Found {len(active_coins)} active tickers:")
    for coin in active_coins:
        print(f"- {coin['korean_name']} ({coin['market']})")
