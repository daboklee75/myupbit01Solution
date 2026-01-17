#!/bin/bash

# Usage: ./run_instance.sh [USER_ID] [PORT]
# Example: ./run_instance.sh friend 8502

USER_ID=$1
PORT=$2

if [ -z "$USER_ID" ] || [ -z "$PORT" ]; then
    echo "Usage: $0 [USER_ID] [PORT]"
    echo "Example: $0 friend 8502"
    exit 1
fi

echo "=========================================="
echo "   Starting UpbitBot for User: $USER_ID   "
echo "   Port: $PORT                            "
echo "=========================================="

# 1. Create User Workspace
# All data (json, logs, .env) will be in users/[USER_ID]/
USER_DIR="users/$USER_ID"
mkdir -p "$USER_DIR"
mkdir -p "$USER_DIR/logs"

# 2. Check for .env file
ENV_FILE="$USER_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "WARNING: .env file not found in $USER_DIR"
    echo "Creating template... Please edit $ENV_FILE with REAL KEYS."
    cp .env.template "$ENV_FILE"
else
    echo "Using existing config: $ENV_FILE"
fi

# 3. Export Environment Variables for Python
# These tell trader.py/app.py where to look for .env and data files.
export MYUPBIT_ENV_FILE="$ENV_FILE"
export MYUPBIT_DATA_DIR="$USER_DIR"

echo "[1/2] Starting Trader Bot..."
# Log to user's log folder
nohup poetry run python src/myupbit01/trader.py > "$USER_DIR/logs/trader.log" 2>&1 &
echo " - Trader started (PID: $!)"

echo "[2/2] Starting Dashboard on Port $PORT..."
nohup poetry run streamlit run src/myupbit01/app.py --server.port $PORT > "$USER_DIR/logs/app.log" 2>&1 &
echo " - Dashboard started (PID: $!)"

echo "=========================================="
echo " Done! Access at http://[SERVER_IP]:$PORT"
echo " IMPORTANT: Edit keys in $ENV_FILE"
echo " Logs at $USER_DIR/logs/"
echo "=========================================="
