#!/bin/bash

echo "Starting MyUpbit Container..."

# Ensure data directory exists
mkdir -p $MYUPBIT_DATA_DIR/logs

# Copy config if not exists
if [ ! -f "$MYUPBIT_DATA_DIR/trader_config.json" ]; then
    echo "Initializing config in data volume..."
    # We assume source config is in /app/src/myupbit01/ or root?
    # Actually trader.py handles copying defaults if I implemented it in app.py logic... 
    # But let's be safe.
    if [ -f "trader_config.json" ]; then
        cp trader_config.json "$MYUPBIT_DATA_DIR/"
    fi
fi

echo "1. Starting Trader..."
# Using unbuffered output (-u) to see logs in docker logs immediately
nohup python -u src/myupbit01/trader.py > "$MYUPBIT_DATA_DIR/logs/trader.log" 2>&1 &

echo "2. Starting Dashboard..."
# Streamlit listens on 8501 by default
nohup streamlit run src/myupbit01/app.py --server.port 8501 --server.address 0.0.0.0 > "$MYUPBIT_DATA_DIR/logs/app.log" 2>&1 &

# Keep container alive by tailing logs
echo "Container Ready. Tailing trader logs..."
tail -f "$MYUPBIT_DATA_DIR/logs/trader.log"
