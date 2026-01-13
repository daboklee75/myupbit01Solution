import streamlit as st
import pandas as pd
import json
import os
import time
import datetime
import pyupbit
from dotenv import load_dotenv

# Load Env
load_dotenv()

# Page Config
st.set_page_config(
    page_title="MyUpbit Trading Bot",
    page_icon="📈",
    layout="wide"
)

# Constants
STATE_FILE = "trade_state.json"
HISTORY_FILE = "trade_history.json"
CONFIG_FILE = "trader_config.json"
COMMAND_FILE = "command.json"
SCAN_RESULTS_FILE = "scan_results.json"
LOG_FILE = "logs/myupbit.log"

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_command(cmd_type, **kwargs):
    cmd = {"command": cmd_type}
    cmd.update(kwargs)
    save_json(COMMAND_FILE, cmd)
    st.toast(f"Command Sent: {cmd_type}")

def load_logs(lines=20):
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                data = f.readlines()
                return "".join(data[-lines:])
        except:
            return "Error loading logs."
    return "No logs found."

def main():
    st.title("🤖 MyUpbit AutoTrader Dashboard")

    # Sidebar: Configuration & Control
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Load Config
        config = load_json(CONFIG_FILE)
        if not config:
            config = {
                "TRADE_AMOUNT": 10000,
                "MAX_SLOTS": 3,
                "COOLDOWN_MINUTES": 60,
                "PROFIT_TARGET": 0.005,
                "STOP_LOSS": -0.02,
                "TRAILING_STOP_CALLBACK": 0.002,
                "ADD_BUY_THRESHOLD": -0.01
            }

        with st.form("config_form"):
            trade_amount = st.number_input("Trade Amount (KRW)", value=float(config.get("TRADE_AMOUNT", 10000)))
            max_slots = st.number_input("Max Slots", value=int(config.get("MAX_SLOTS", 3)))
            cooldown = st.number_input("Cooldown (min)", value=int(config.get("COOLDOWN_MINUTES", 60)))
            profit_target = st.slider("Profit Target (%)", 0.1, 5.0, float(config.get("PROFIT_TARGET", 0.005)) * 100) / 100
            stop_loss = st.slider("Stop Loss (%)", -10.0, -0.1, float(config.get("STOP_LOSS", -0.02)) * 100) / 100
            trailing_callback = st.slider("Trailing Callback (%)", 0.1, 2.0, float(config.get("TRAILING_STOP_CALLBACK", 0.002)) * 100) / 100
            add_buy_threshold = st.slider("Add-Buy Threshold (%)", -10.0, -0.1, float(config.get("ADD_BUY_THRESHOLD", -0.01)) * 100) / 100
            
            if st.form_submit_button("Update Config"):
                new_config = {
                    "TRADE_AMOUNT": trade_amount,
                    "MAX_SLOTS": max_slots,
                    "COOLDOWN_MINUTES": cooldown,
                    "PROFIT_TARGET": profit_target,
                    "STOP_LOSS": stop_loss,
                    "TRAILING_STOP_CALLBACK": trailing_callback,
                    "ADD_BUY_THRESHOLD": add_buy_threshold
                }
                save_json(CONFIG_FILE, new_config)
                st.success("Config updated!")

        st.divider()
        st.header("🎮 Manual Control")
        col_c1, col_c2 = st.columns(2)
        if col_c1.button("🛑 Stop Bot"):
            send_command("master_stop")
        if col_c2.button("▶️ Start Bot"):
            send_command("master_start")

        st.caption("Master switch controls new entries only.")

    # Auto Refresh Checkbox (Logic at end)
    auto_refresh = st.checkbox("Auto Refresh (10s)", value=True)

    # Load Main Data
    state = load_json(STATE_FILE)
    history = load_json(HISTORY_FILE) # Actually this loads a list, need logic
    if isinstance(history, dict): history = [] # Handle if file init wrong
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Real-time Status", "🔍 Scanner", "📈 Balance Metrics", "📅 Stats & History", "📝 Logs"])

    with tab1:
        st.subheader("Active Trading Slots")
        slots = state.get("slots", [])
        
        if not slots:
            st.info("No active trades currently.")
        else:
            for slot in slots:
                market = slot.get('market')
                status = slot.get('status')
                avg_price = slot.get('avg_buy_price', 0)
                
                # Fetch current info
                current_price = pyupbit.get_current_price(market) or 0
                
                # Fetch balance to calculate total value
                balance = 0
                try:
                    access = os.getenv("UPBIT_ACCESS_KEY")
                    secret = os.getenv("UPBIT_SECRET_KEY")
                    # We need a fresh instance or reuse one. Creating new for safety in loop (low overhead)
                    upbit = pyupbit.Upbit(access, secret)
                    balance = upbit.get_balance(market)
                except:
                    balance = 0

                invested_amount = balance * avg_price
                current_value = balance * current_price
                
                profit_rate = 0.0
                if avg_price > 0 and current_price > 0:
                    profit_rate = (current_price - avg_price) / avg_price
                
                with st.container(border=True):
                    c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 2, 2, 2])
                    c1.metric("Market", market, status)
                    c2.metric("Return", f"{profit_rate*100:.2f}%", f"{current_value - invested_amount:,.0f} KRW")
                    c3.metric("Current Price", f"{current_price:,.0f}")
                    c4.metric("Entry Price", f"{avg_price:,.0f}")
                    c5.metric("Invested", f"{invested_amount:,.0f} KRW")
                    
                    if c6.button("🚨 Panic Sell", key=f"panic_{market}"):
                        send_command("panic_sell", market=market)

        st.subheader("Cooldowns")
        st.write(state.get("cooldowns", {}))

    with tab2:
        st.subheader("Scanner Candidates (Strict)")
        scan_res = load_json(SCAN_RESULTS_FILE)
        timestamp = scan_res.get("timestamp", "-")
        st.caption(f"Last Scan: {timestamp}")
        
        candidates = scan_res.get("candidates", [])
        if candidates:
            df_scan = pd.DataFrame(candidates)
            # Reorder cols
            cols = ['korean_name', 'market', 'score', 'price', 'is_aligned_full', 'sma5_slope_up', 'volatility_rising', 'adx', 'vol_spike']
            # Filter cols that exist
            cols = [c for c in cols if c in df_scan.columns]
            
            st.dataframe(df_scan[cols], use_container_width=True)
            
            st.caption("Score Guide: Aligned(5/10) + Slope(10) + Vol(5) + ADX(5) + Spike(10) + Orderbook(5) + Trade(10)")
        else:
            st.info("No candidates found in last scan.")

    with tab3:
        st.subheader("Asset Balance")
        try:
            # Fetch balances (Caution: API limit)
            access = os.getenv("UPBIT_ACCESS_KEY")
            secret = os.getenv("UPBIT_SECRET_KEY")
            upbit = pyupbit.Upbit(access, secret)
            balances = upbit.get_balances()
            
            if balances:
                df_bal = pd.DataFrame(balances)
                df_bal['balance'] = df_bal['balance'].astype(float)
                df_bal['avg_buy_price'] = df_bal['avg_buy_price'].astype(float)
                
                # Get current prices for total value
                total_krw = 0
                pie_data = []
                
                for idx, row in df_bal.iterrows():
                    currency = row['currency']
                    if currency == "KRW":
                        val = row['balance']
                        total_krw += val
                        pie_data.append({"Currency": "KRW", "Value": val})
                    else:
                        # Estimate value
                        ticker = f"KRW-{currency}"
                        curr_p = pyupbit.get_current_price(ticker)
                        if curr_p:
                            val = row['balance'] * curr_p
                            total_krw += val
                            pie_data.append({"Currency": currency, "Value": val})
                        else:
                            # Use avg buy price if current not avail
                            val = row['balance'] * row['avg_buy_price']
                            total_krw += val
                            pie_data.append({"Currency": currency, "Value": val})

                st.metric("Total Asset Value (Est.)", f"{total_krw:,.0f} KRW")
                
                c1, c2 = st.columns(2)
                c1.dataframe(df_bal[['currency', 'balance', 'avg_buy_price']], use_container_width=True)
                
                df_pie = pd.DataFrame(pie_data)
                c2.write("Asset Allocation")
                # Pie chart simple
                st.bar_chart(df_pie.set_index("Currency"))
                
        except Exception as e:
            st.error(f"Error fetching balances: {e}")

    with tab4:
        st.subheader("Daily History")
        if isinstance(history, list) and history:
            df_hist = pd.DataFrame(history)
            st.dataframe(df_hist.sort_values('time', ascending=False), use_container_width=True)
        else:
            st.info("No history.")

    with tab5:
        st.subheader("System Logs")
        logs = load_logs(30)
        st.code(logs)

    # Auto refresh timer loop logic is handled here at the end
    if auto_refresh:
        time.sleep(10)
        st.rerun()

if __name__ == "__main__":
    main()
