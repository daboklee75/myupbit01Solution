#!/bin/bash

echo "=========================================="
echo "   MyUpbit01 Restart Script (Linux/AWS)   "
echo "=========================================="

echo "[1/4] Stopping existing processes..."
# Kill only if they exist to avoid 'no process found' messages cluttering output
pgrep -f trader.py > /dev/null && pkill -f trader.py && echo " - Stopped trader.py"
pgrep -f streamlit > /dev/null && pkill -f streamlit && echo " - Stopped streamlit"

echo "[2/4] Waiting for ports to clear..."
sleep 2

# Ensure log directory exists
mkdir -p logs

echo "[3/4] Starting Trader Bot..."
nohup poetry run python src/myupbit01/trader.py > logs/trader.log 2>&1 &
echo " - Trader started (PID: $!)"

echo "[4/4] Starting Dashboard..."
nohup poetry run streamlit run src/myupbit01/app.py > logs/app.log 2>&1 &
echo " - Dashboard started (PID: $!)"

echo "=========================================="
echo " Done! Logs are in ./logs/"
echo "=========================================="
