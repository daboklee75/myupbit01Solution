import os
from dotenv import load_dotenv
from myupbit01.trader import AutoTrader

def main():
    load_dotenv()
    
    access_key = os.getenv("UPBIT_ACCESS_KEY")
    secret_key = os.getenv("UPBIT_SECRET_KEY")
    
    if not (access_key and secret_key):
        print("Error: API keys not found in .env file.")
        return

    print("Keys loaded successfully.")
    
    try:
        trader = AutoTrader()
        trader.run()
    except KeyboardInterrupt:
        print("Terminating...")

if __name__ == "__main__":
    main()
