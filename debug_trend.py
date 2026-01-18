
import sys
import os

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, "src")
sys.path.append(src_dir)

from dotenv import load_dotenv
import json
from myupbit01 import trend

# Load environment variables
load_dotenv()

def run_debug_search():
    print("=== Debugging Market Search (Dry Run) ===")
    
    # Check API Keys
    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")
    if not access or not secret:
        print("CRITICAL: API Keys missing in .env")
        return

    # Load Config
    config_file = "trader_config.json"
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        print("Config file not found, using defaults.")
        config = {}

    # Override for raw debug (User Request)
    min_score = 0
    min_slope = -10.0 
    
    print(f"Configuration (Refreshed): Min Score = {min_score} (Unfiltered), Min Slope = {min_slope}% (Unfiltered)")
    
    try:
        # Run Search
        print("Fetching ranked targets...")
        targets = trend.get_ranked_targets(min_score=min_score, limit=30, min_slope=min_slope)
        
        if targets:
            print("\n=== Found Targets ===")
            for i, t in enumerate(targets):
                print(f"[{i+1}] {t['korean_name']} ({t['market']})")
                print(f"    Score: {t['score']}")
                print(f"    Slope: {t['slope']:.2f}%")
                print(f"    RSI: {t['rsi']:.1f}")
                print(f"    Vol Ratio: {t['vol_ratio']:.2f}")
                print(f"    Channel Pos: {t['channel_pos']:.2f}")
                print("-" * 30)
        else:
            print("\n=== No Targets Found ===")
            print("Possible reasons:")
            print("1. Market is flat (Low Slopes)")
            print("2. Recent pump dumps (Low Scores)")
            print("3. API limits or Network issues")
            
    except Exception as e:
        print(f"Error during search: {e}")

if __name__ == "__main__":
    run_debug_search()
