import os
import sys
import time
from dotenv import load_dotenv
from myupbit01.trader import AutoTrader

LOCK_FILE = "myupbit.lock"
lock_file_handle = None

def acquire_lock():
    global lock_file_handle
    lock_file_handle = open(LOCK_FILE, 'w')
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.lockf(lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, BlockingIOError, PermissionError):
        print("Program is already running! (Lock file is occupied)")
        sys.exit(1)

def main():
    # 1. Acquire Lock
    acquire_lock()
    
    # 2. Load environment variables
    load_dotenv()
    
    access_key = os.getenv("UPBIT_ACCESS_KEY")
    secret_key = os.getenv("UPBIT_SECRET_KEY")
    
    if not (access_key and secret_key):
        print("Error: API keys not found in .env file.")
        return

    if "your_access_key" in access_key or "your_secret_key" in secret_key:
        print("Error: Default API keys detected. Please update .env with real keys.")
        return
        
    if len(access_key) < 20 or len(secret_key) < 20: 
        print("Error: API keys seem too short. Please check .env file.")
        return

    print("Keys loaded successfully.")
    
    try:
        trader = AutoTrader()
        trader.run()
    except KeyboardInterrupt:
        print("Terminating...")

import logging
from myupbit01.logger import setup_logger

if __name__ == "__main__":
    setup_logger()
    logger = logging.getLogger("MyUpbit")
    logger.info("=== Program Started ===")
    try:
        main()
    except Exception as e:
        logger.error(f"Program crashed: {e}", exc_info=True)
    finally:
        logger.info("=== Program Ended ===")
