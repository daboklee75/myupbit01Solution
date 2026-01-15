import logging
import os
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = "logs"

def setup_logger(name="MyUpbit"):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
        
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid adding handlers multiple times
    if logger.hasHandlers():
        return logger
    
    # Daily rotation
    handler = TimedRotatingFileHandler(
        filename=os.path.join(LOG_DIR, "myupbit.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    handler.suffix = "%Y-%m-%d"
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger
