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

    print("Keys loaded successfully.")
    
    try:
        trader = AutoTrader()
        trader.run()
    except KeyboardInterrupt:
        print("Terminating...")

if __name__ == "__main__":
    main()
