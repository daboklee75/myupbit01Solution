@echo off
echo Starting MyUpbit AutoTrader and Dashboard...

:: Start Trader Bot in a new window
start "MyUpbit Bot" cmd /k "poetry run python src/myupbit01/main.py"

:: Wait a few seconds for bot to initialize
timeout /t 5

:: Start Dashboard in a new window
start "MyUpbit Dashboard" cmd /k "poetry run streamlit run src/myupbit01/app.py"

echo Done.
