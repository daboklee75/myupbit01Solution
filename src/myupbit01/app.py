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

# Custom CSS for Compact Layout
st.markdown("""
<style>
    /* Reduce main container padding */
    .block-container {
        padding-top: 3rem !important; /* Increased to fix title cutoff */
        padding-bottom: 1rem !important;
    }
    /* Compact Metrics */
    div[data-testid="stMetric"] {
        padding: 5px !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.8rem !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.1rem !important;
    }
    /* Compact Expander */
    .streamlit-expanderHeader {
        padding-top: 5px !important;
        padding-bottom: 5px !important;
        min-height: 40px !important;
    }
    .streamlit-expanderContent {
        padding-top: 5px !important;
        padding-bottom: 5px !important;
    }
    /* Reduce vertical gaps between elements */
    div[data-testid="stVerticalBlock"] > div {
        margin-bottom: 0.1rem !important;
    }
    h1, h2, h3 {
        margin-top: 0px !important;
        margin-bottom: 5px !important;
        padding: 0px !important;
    }
    /* Compact Bordered Container (Panel Box) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.5rem !important; /* Reduced for tighter look */
        margin-bottom: 0.2rem !important;
        background-color: #f9f9faf0;
    }
    /* Target the inner content of the bordered container to remove extra padding */
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        padding-top: 0px !important;
        padding-bottom: 0px !important;
    }
</style>
""", unsafe_allow_html=True)

# Debug helper to inspect balances
def debug_balances():
    try:
        access = os.getenv("UPBIT_ACCESS_KEY")
        secret = os.getenv("UPBIT_SECRET_KEY")
        if not access or not secret:
            return "API Keys missing in .env"
        
        upbit = pyupbit.Upbit(access, secret)
        balances = upbit.get_balances()
        return balances
    except Exception as e:
        return f"Error: {e}"


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

@st.cache_data(ttl=60)
def load_balances_cached():
    """
    Fetch balances and current prices with caching to prevent API rate limits and UI lag.
    """
    try:
        access = os.getenv("UPBIT_ACCESS_KEY")
        secret = os.getenv("UPBIT_SECRET_KEY")
        if not access or not secret:
            return None, [], 0

        upbit = pyupbit.Upbit(access, secret)
        balances = upbit.get_balances()
        
        if not balances:
            return None, [], 0

        df_bal = pd.DataFrame(balances)
        df_bal['balance'] = df_bal['balance'].astype(float)
        df_bal['avg_buy_price'] = df_bal['avg_buy_price'].astype(float)
        
        total_krw = 0
        pie_data = []
        
        # Optimize: Batch price fetch if possible, but pyupbit.get_current_price(list) works?
        # Let's collect tickers first
        tickers = []
        for idx, row in df_bal.iterrows():
            if row['currency'] != "KRW":
                tickers.append(f"KRW-{row['currency']}")
        
        current_prices = {}
        if tickers:
            current_prices = pyupbit.get_current_price(tickers)
            if not isinstance(current_prices, dict):
                # if single result or None, handle carefully. 
                # get_current_price list returns dict {ticker: price} normally.
                if isinstance(current_prices, float) or isinstance(current_prices, int):
                     current_prices = {tickers[0]: current_prices}
                elif current_prices is None:
                     current_prices = {}

        for idx, row in df_bal.iterrows():
            currency = row['currency']
            if currency == "KRW":
                val = row['balance']
                total_krw += val
                pie_data.append({"Currency": "KRW", "Value": val})
            else:
                ticker = f"KRW-{currency}"
                curr_p = current_prices.get(ticker, 0)
                
                if curr_p > 0:
                    val = row['balance'] * curr_p
                    total_krw += val
                    pie_data.append({"Currency": currency, "Value": val})
                else:
                    # Fallback to avg buy price
                    val = row['balance'] * row['avg_buy_price']
                    total_krw += val
                    pie_data.append({"Currency": currency, "Value": val})
                    
        return df_bal, pie_data, total_krw
    except Exception as e:
        return None, [], 0

@st.cache_data(ttl=60)
def process_history_data(history, trade_amt_default):
    """
    Process raw history data into a DataFrame with calculated metrics.
    Cached to avoid re-calculation on every render.
    """
    if not history:
        return pd.DataFrame()
        
    df = pd.DataFrame(history)
    
    # 1. Date Conversion
    if 'date' in df.columns:
        df['date_dt'] = pd.to_datetime(df['date']).dt.date
    
    # 2. PnL Calculation
    if 'pnl' not in df.columns:
        df['pnl'] = df['profit_rate'] * trade_amt_default
        
    # 3. Sell Price Calculation
    if 'sell_price' not in df.columns:
        df['sell_price'] = df['buy_price'] * (1 + df['profit_rate'])
        
    # 4. Analysis Generation
    def generate_analysis(row):
        reason = row.get('reason', '')
        pnl_rate = row.get('profit_rate', 0)
        
        analysis = ""
        if "Trailing Stop" in reason:
            analysis = "🟢 [성공] 목표 수익 도달 후 익절"
        elif "Stop Loss" in reason:
            analysis = "🔴 [손절] 손실 제한 매도 실행"
        elif "Sudden Drop" in reason:
            analysis = "🛡️ [방어] 급락 감지되어 긴급 매도"
        elif pnl_rate > 0:
            analysis = "🟢 [익절] 수익 실현"
        else:
            analysis = "⚪ [매도] 기타 사유"
        
        # Add-Buy Info
        trade_log = row.get('trade_history_log', [])
        entry_cnt = row.get('entry_cnt', 1)
        
        if isinstance(trade_log, list) and trade_log:
            # New format with log
            adds = [item for item in trade_log if item.get('type') == 'Add']
            if adds:
                prices = []
                for a in adds:
                    p = float(a.get('price', 0))
                    # Use sufficient precision
                    p_str = f"{p:,.4f}" if p < 100 else f"{p:,.1f}" if p < 1000 else f"{p:,.0f}"
                    prices.append(p_str)
                analysis += f"\n(물타기: {len(adds)}회 @ {', '.join(prices)})"
        elif entry_cnt > 1:
            # Legacy format
            analysis += f"\n(물타기: {entry_cnt-1}회)"
            
        return analysis
            
    df['Analysis'] = df.apply(generate_analysis, axis=1)
    
    # 5. Formatting
    df['Return (%)'] = df.apply(
        lambda row: f"{row['profit_rate']*100:+.2f}% ({row['pnl']:+,.0f} KRW)", axis=1
    )
    
    def fmt_price_col(x):
        return f"{x:,.4f}" if x < 100 else f"{x:,.1f}" if x < 1000 else f"{x:,.0f}"

    df['Sell Price'] = df['sell_price'].apply(fmt_price_col)
    df['Buy Price'] = df['buy_price'].apply(fmt_price_col)
    
    return df

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

def check_password():
    """Returns `True` if the user had the correct password."""
    
    # Credentials from .env
    correct_user = os.getenv("WEB_USERNAME")
    correct_password = os.getenv("WEB_PASSWORD")

    # If no credentials set, warn but allow (or return False to force setup? Let's allow for now to prevent lockout if env not set)
    if not correct_user or not correct_password:
        # st.warning("⚠️ .env 파일에 WEB_USERNAME과 WEB_PASSWORD가 설정되지 않았습니다.")
        return True

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["username"] == correct_user and st.session_state["password"] == correct_password:
            st.session_state["password_correct"] = True
            # Clear inputs
            del st.session_state["password"]
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 로그인 (Login)")
        
        with st.form("login_form"):
            st.text_input("아이디 (Username)", key="username")
            st.text_input("비밀번호 (Password)", type="password", key="password")
            if st.form_submit_button("로그인", on_click=password_entered):
                pass # Logic handled in on_click
                
        if "password_correct" in st.session_state and st.session_state["password_correct"] == False:
            st.error("😕 아이디 또는 비밀번호가 틀렸습니다.")
            
        return False
        
    return True

def main():
    if not check_password():
        st.stop()

    st.title("🤖 MyUpbit AutoTrader Dashboard")

    # Sidebar: Configuration & Control
    with st.sidebar:
        # User Profile & Logout
        if os.getenv("WEB_USERNAME"):
            st.caption(f"👤 {os.getenv('WEB_USERNAME')} 로그인 중")
            if st.button("🚪 로그아웃", use_container_width=True):
                st.session_state["password_correct"] = False
                st.rerun()
            st.divider()

        st.header("⚙️ 설정 (Settings)")
        
        # Load Config
        config = load_json(CONFIG_FILE)
        if not config:
            config = {}

        with st.form("config_form"):
            trade_amount = st.number_input("1회 매수 금액 (KRW)", value=float(config.get("TRADE_AMOUNT", 10000)))
            max_slots = st.number_input("최대 보유 종목 수", value=int(config.get("MAX_SLOTS", 3)))
            cooldown = st.number_input("재진입 대기 시간 (분)", value=int(config.get("COOLDOWN_MINUTES", 60)))
            
            # Updated Strategy Configs
            st.divider()
            # Updated Strategy Configs
            st.divider()
            st.subheader("🛡️ 시장 방어 필터 (비트코인 연동)")
            market_filter = config.get("market_filter", {})
            use_btc_filter = st.checkbox("비트코인 연동 방어 사용", value=market_filter.get("use_btc_filter", True))
            
            if use_btc_filter:
                btc_drop_val = float(market_filter.get("btc_1h_drop_threshold", -0.015)) * 100
                btc_drop_threshold = st.slider("BTC 1시간 급락 감지 (%)", -5.0, -0.5, btc_drop_val) / 100
                
                btc_slope_val = float(market_filter.get("btc_3h_slope_threshold", -0.5))
                btc_slope_threshold = st.slider("BTC 3시간 추세 이탈 감지 (%)", -2.0, -0.1, btc_slope_val, step=0.1)
            else:
                btc_drop_threshold = -0.015
                btc_slope_threshold = -0.5

            st.divider()
            st.subheader("전략 설정")
            # Score
            min_entry_score = st.number_input("최소 진입 점수", value=int(config.get("MIN_ENTRY_SCORE", 30)))
            
            # [NEW] Slope
            min_slope_val = float(config.get("min_slope_threshold", 0.5))
            min_slope = st.slider("최소 추세 기울기 (Slope %)", -1.0, 3.0, min_slope_val, step=0.1)
            
            # Exit Strategy
            exit_strategies = config.get("exit_strategies", {})
            st.divider()
            st.subheader("청산 전략 (고급)")
            # [NEW] TP Ratio
            tp_ratio = st.slider("익절 비율 (전고점 대비 %)", 10, 100, int(float(exit_strategies.get("take_profit_ratio", 0.5)) * 100)) / 100.0
            
            stop_loss = st.slider("손절 기준 (%)", -30.0, -0.1, float(exit_strategies.get("stop_loss", 0.05)) * -100) / -100
            trailing_trigger = st.slider("트레일링 시작 (%)", 0.1, 5.0, float(exit_strategies.get("trailing_stop_trigger", 0.008)) * 100) / 100
            trailing_gap = st.slider("트레일링 감지 폭 (%)", 0.1, 2.0, float(exit_strategies.get("trailing_stop_gap", 0.002)) * 100) / 100
            
            # Add-Buy Config
            st.markdown("#### 💧 물타기 설정 (Add-Buy)")
            max_add_buys = st.number_input("물타기 최대 횟수 (0 = 사용 안 함)", min_value=0, max_value=10, value=int(exit_strategies.get("max_add_buys", 0)))
            
            if max_add_buys == 0:
                st.caption("🚫 물타기 기능이 꺼져 있습니다. (칼손절 모드)")
                add_buy_trigger = float(exit_strategies.get("add_buy_trigger", -0.05)) # Keep current val visible but disabled concept
            else:
                add_buy_val = float(exit_strategies.get("add_buy_trigger", -0.03)) * 100
                add_buy_trigger = st.slider("물타기 (Add-Buy) 기준 (%)", -20.0, -0.5, add_buy_val) / 100
            
            # [NEW] Add-Buy Amount Ratio
            ab_amt_val = int(float(exit_strategies.get("add_buy_amount_ratio", 1.0)) * 100)
            add_buy_amt_ratio = st.slider("물타기 금액 비율 (1회 진입금 대비 %)", 10, 300, ab_amt_val) / 100.0

            if st.form_submit_button("설정 업데이트"):
                # Preserve existing structure
                config["TRADE_AMOUNT"] = trade_amount
                config["MAX_SLOTS"] = max_slots
                config["COOLDOWN_MINUTES"] = cooldown
                config["MIN_ENTRY_SCORE"] = min_entry_score
                config["min_slope_threshold"] = min_slope # [NEW]
                
                # Update nested exit strategies
                if "exit_strategies" not in config: config["exit_strategies"] = {}
                
                # Store normalized values
                config["exit_strategies"]["take_profit_ratio"] = tp_ratio
                config["exit_strategies"]["stop_loss"] = abs(stop_loss)
                config["exit_strategies"]["trailing_stop_trigger"] = trailing_trigger
                config["exit_strategies"]["trailing_stop_gap"] = trailing_gap
                config["exit_strategies"]["max_add_buys"] = max_add_buys # [NEW]
                config["exit_strategies"]["add_buy_trigger"] = add_buy_trigger
                config["exit_strategies"]["add_buy_amount_ratio"] = add_buy_amt_ratio
                config["exit_strategies"]["add_buy_amount_ratio"] = add_buy_amt_ratio
                
                # Update Market Filter
                if "market_filter" not in config: config["market_filter"] = {}
                config["market_filter"]["use_btc_filter"] = use_btc_filter
                config["market_filter"]["btc_1h_drop_threshold"] = btc_drop_threshold
                config["market_filter"]["btc_3h_slope_threshold"] = btc_slope_threshold
                
                # Save config
                save_json(CONFIG_FILE, config)
                st.success("설정이 업데이트되었습니다! (자동 반영)")
                time.sleep(1)
                st.rerun()

        st.divider()
        st.header("🎮 수동 제어")
        col_c1, col_c2 = st.columns(2)
        if col_c1.button("🛑 봇 정지"):
            send_command("master_stop")
        if col_c2.button("▶️ 봇 시작"):
            send_command("master_start")

        st.caption("마스터 스위치는 신규 진입만 제어합니다.")

    # Auto Refresh Checkbox (Logic at end)
    auto_refresh = st.checkbox("자동 새로고침 (10초)", value=True)

    # Load Main Data
    state = load_json(STATE_FILE)
    history = load_json(HISTORY_FILE) 
    if isinstance(history, dict): history = [] 
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 실시간 현황", "🔍 종목 스캐너", "📈 자산 분석", "📅 거래 기록", "📝 로그"])

    with tab1:
        st.subheader("진행 중인 거래 (Active Slots)")
        slots = state.get("slots", [])
        
        if not slots:
            st.info("현재 진행 중인 거래가 없습니다.")
        else:
            # Optimize: Create Upbit instance and fetch balances ONCE
            balance_map = {}
            try:
                access = os.getenv("UPBIT_ACCESS_KEY")
                secret = os.getenv("UPBIT_SECRET_KEY")
                if access and secret:
                     upbit = pyupbit.Upbit(access, secret)
                     balances = upbit.get_balances()
                     # Valid response is a list
                     if isinstance(balances, list):
                         for b in balances:
                             currency = b.get('currency')
                             # Total = Available + Locked
                             total_qty = float(b.get('balance', 0)) + float(b.get('locked', 0))
                             avg_price = float(b.get('avg_buy_price', 0))
                             balance_map[currency] = {
                                 'qty': total_qty,
                                 'avg_price': avg_price
                             }
            except Exception as e:
                st.error(f"Wallet Fetch Error: {e}")

            # 1. Pre-calculate Totals & Prepare Data
            total_invested_all = 0.0
            total_current_all = 0.0
            slot_display_data = []

            for slot in slots:
                market = slot.get('market')
                status = slot.get('status')
                # Use saved avg price from slot as primary, fallback to wallet
                avg_price = slot.get('avg_buy_price', 0)
                
                # Fetch current info
                try:
                    current_price = pyupbit.get_current_price(market) or 0
                except Exception:
                    current_price = 0
                
                # Fetch balance from pre-fetched map
                total_qty = 0
                try:
                    currency = market.split('-')[1]
                    if currency in balance_map:
                        total_qty = balance_map[currency]['qty']
                        # If slot avg price is 0 (missing), try to use wallet avg price
                        if avg_price == 0:
                            avg_price = balance_map[currency]['avg_price']
                except:
                    total_qty = 0

                # Calculate Values
                balance = total_qty # Use total quantity (locked + available)
                invested_amount = balance * avg_price
                current_value = balance * current_price
                
                # Add to Totals
                total_invested_all += invested_amount
                total_current_all += current_value

                # Store for rendering
                slot_display_data.append({
                    "slot": slot,
                    "market": market,
                    "status": status,
                    "avg_price": avg_price,
                    "current_price": current_price,
                    "balance": balance,
                    "invested_amount": invested_amount,
                    "current_value": current_value
                })

            # 2. Display Totals Header
            tot_c1, tot_c2, tot_c3 = st.columns(3)
            tot_c1.metric("총 매수금액 (Total Invested)", f"{total_invested_all:,.0f} KRW")
            tot_c2.metric("총 평가금액 (Total Value)", f"{total_current_all:,.0f} KRW")
            
            total_pnl_val = total_current_all - total_invested_all
            total_pnl_rate = (total_pnl_val / total_invested_all * 100) if total_invested_all > 0 else 0
            tot_c3.metric("총 평가손익 (Total PnL)", f"{total_pnl_val:+,.0f} KRW", f"{total_pnl_rate:+.2f}%")
            
            st.divider()

            # 3. Render Individual Slots
            for data in slot_display_data:
                slot = data["slot"]
                market = data["market"]
                status = data["status"]
                avg_price = data["avg_price"]
                current_price = data["current_price"]
                balance = data["balance"]
                invested_amount = data["invested_amount"]
                current_value = data["current_value"]

                # Calculate Profit & Trailing Info
                entry_price = float(slot.get('avg_buy_price', 0))
                highest_price = float(slot.get('highest_price', entry_price)) # Need to ensure trader saves this
                profit_rate = 0.0
                
                if entry_price > 0 and current_price > 0:
                    profit_rate = (current_price - entry_price) / entry_price
                    
                # Trailing Check
                exit_cfg = config.get("exit_strategies", {})
                profit_target = float(exit_cfg.get("trailing_stop_trigger", 0.012))
                max_profit_rate = 0.0
                if entry_price > 0:
                    max_profit_rate = (highest_price - entry_price) / entry_price

                is_trailing_active = max_profit_rate >= profit_target
                
                # Status Mapping
                status_map = {
                    "BUY_WAIT": "🕒 매수 대기 (주문 중)",
                    "HOLDING": "💰 보유 중 (수익 감시)",
                    "SELL_WAIT": "⏳ 매도 대기 (주문 중)"
                }
                status_kr = status_map.get(status, status)
                
                # Visual Distinction (Colors)
                status_color = "gray"
                if status == "HOLDING":
                    status_color = "green"
                elif status == "BUY_WAIT":
                    status_color = "orange"
                
                with st.container(border=True):
                    # Header with Status Badge
                    c_head1, c_edit, c_panic = st.columns([2.5, 1.2, 0.8])
                    
                    # Custom HTML Badge
                    badge_html = f"""
                    <span style='
                        background-color: {status_color};
                        color: white;
                        padding: 4px 8px;
                        border-radius: 4px;
                        font-size: 0.8em;
                        font-weight: bold;
                        vertical-align: middle;
                        margin-left: 8px;
                        margin-bottom: 3px;
                    '>{status_kr}</span>
                    """
                    
                    # Korean Name (Safe Access)
                    korean_name = slot.get('trend_info', {}).get('korean_name', '')
                    if not korean_name:
                         # Fallback if trend_info missing or empty
                         korean_name = ""
                    else:
                        korean_name = f"({korean_name})"

                    # Title Construction with Korean Name
                    title_html = f"""
                    <div style='display: flex; align-items: center; margin-bottom: 0px;'>
                        <h3 style='margin: 0; padding: 0;'>{market} <span style='font-size: 0.8em; font-weight: normal; color: #555;'>{korean_name}</span></h3>
                        {badge_html}
                    </div>
                    """
                    
                    if is_trailing_active:
                         title_html += "<div style='font-size: 0.8em; color: red; margin-top: 2px;'>🔥 익절 감시 중 (Trailing)</div>"

                    c_head1.markdown(title_html, unsafe_allow_html=True)
                    
                    if status == "BUY_WAIT":
                         if c_panic.button("🚫 취소 (Cancel)", key=f"cancel_{market}"):
                             send_command("cancel_buy_order", market=market)
                    else:
                        # HOLDING
                        # [NEW] Manual Sell Price Edit in Header
                        with c_edit:
                            with st.expander("✏️ 수정", expanded=False):
                                sell_price_display = float(slot.get('sell_limit_price', 0))
                                default_sp = sell_price_display if sell_price_display > 0 else current_price * 1.01
                                new_sp = st.number_input(
                                    "가격", 
                                    value=float(default_sp), 
                                    min_value=float(current_price * 0.5), 
                                    step=0.0001 if default_sp < 100 else 1.0,
                                    format="%.4f" if default_sp < 100 else "%.0f",
                                    key=f"sp_input_head_{market}",
                                    label_visibility="collapsed"
                                )
                                if st.button("수정", key=f"sp_btn_head_{market}"):
                                    if new_sp > 0:
                                        send_command("update_sell_order", market=market, price=new_sp)
                                        st.success(f"{new_sp}")
                        
                        if c_panic.button("🚨 긴급 매도", key=f"panic_{market}"):
                            send_command("panic_sell", market=market)

                    c1, c2, c3, c4, c5 = st.columns(5)
                    
                    # Uniform Layout: 
                    # 1. Profit (수익률)
                    # 2. Current (현재가)
                    # 3. Buy/Order (매수가/주문가)
                    # 4. Sell/- (매도예약/-)
                    # 5. Total Value (평가금액/주문총액)
                    
                    # Common Metrics
                    c1.metric("수익률 (Return)", f"{profit_rate*100:.2f}%")
                    c2.metric("현재가 (Price)", f"{current_price:,.4f}") # Removed high price
                    
                    if status == "HOLDING":
                         
                         entry_cnt = slot.get('entry_cnt', 1)
                         trade_log = slot.get('trade_history_log', [])
                         
                         sub_text = ""
                         
                         # Helper for consistent price formatting
                         def fmt_p(p):
                             return f"{p:,.0f}" if p >= 100 else f"{p:,.2f}"

                         if trade_log:
                             # Format: Init 01.19(74) / Add 01.19(66)
                             parts = []
                             for item in trade_log:
                                 t_type = item.get('type', 'Buy') # Init or Add
                                 t_price = float(item.get('price', 0))
                                 t_time = item.get('time', '') # MM.DD
                                 
                                 # Format Type (Init/Add usually)
                                 display_type = "Init" if t_type == "Init" else "Add"
                                 
                                 parts.append(f"{display_type} {t_time}({fmt_p(t_price)})")
                                 
                             sub_text = " / ".join(parts)
                         elif entry_cnt > 1:
                             # Legacy Fallback (Multi-step but no log)
                             init_p = float(slot.get('initial_buy_price', entry_price))
                             water_p = float(slot.get('water_buy_price', 0))
                             
                             if water_p > 0:
                                 # Init: 100 / Add: 90
                                 sub_text = f"Init({fmt_p(init_p)}) / Add({fmt_p(water_p)})"
                             else:
                                 sub_text = f"Init({fmt_p(init_p)})"
                         else:
                             # Single Entry (Legacy or just started)
                             # Show Init price same as entry price
                             sub_text = f"Init({fmt_p(entry_price)})"
                                 
                         c3.metric("매수가 (평단/상세)", f"{entry_price:,.4f}", sub_text, delta_color="off")
                         
                         sell_price_display = float(slot.get('sell_limit_price', 0))
                         sell_msg = "-"
                         if sell_price_display > 0:
                              # Expected profit calculation
                              exp_profit = ((sell_price_display - entry_price) / entry_price) * 100
                              
                              # Adaptive formatting
                              if sell_price_display < 100:
                                  price_fmt = "{:,.4f}"
                              else:
                                  price_fmt = "{:,.0f}"
                              
                              sell_msg = f"{price_fmt.format(sell_price_display)} ({exp_profit:.1f}%)"
                             
                         c4.metric("매도예약 (Sell)", sell_msg)
                         
                         # Value: 9,933 KRW (10,000 KRW)
                         c5.metric("평가총금액 (Value)", f"{current_value:,.0f} KRW ({invested_amount:,.0f} KRW)", f"{current_value - invested_amount:,.0f} KRW")
                         
                    else:
                        # BUY_WAIT
                        limit_price = float(slot.get('limit_price', entry_price))
                        c3.metric("주문가 (Limit)", f"{limit_price:,.4f}")
                        
                        c4.metric("매도예약 (Sell)", "-")
                        
                        order_amount = float(config.get("TRADE_AMOUNT", 10000))
                        c5.metric("주문총금액 (Order)", f"{order_amount:,.0f} KRW")

                    if is_trailing_active:
                        st.progress(min(max_profit_rate / (profit_target * 2), 1.0), text=f"최고 수익률: {max_profit_rate*100:.2f}% (목표: {profit_target*100:.2f}%)")

        st.subheader("재진입 대기 (Cooldowns)")
        st.write(state.get("cooldowns", {}))

        with st.expander("🛠️ 지갑 디버깅 (Wallet Debug)"):
             if st.button("내 잔고 전체 조회"):
                 st.write(debug_balances())


    with tab2:
        st.subheader("실시간 랭킹 (Ranked Candidates)")
        scan_res = load_json(SCAN_RESULTS_FILE)
        timestamp = scan_res.get("timestamp", "-")
        st.caption(f"마지막 검색: {timestamp}")
        
        candidates = scan_res.get("candidates", [])
        if candidates:
            # df_scan = pd.DataFrame(candidates) # Removed duplicate line
            df_scan = pd.DataFrame(candidates)
            # Reorder cols
            # cols = ['korean_name', 'score', 'rsi', 'buy_ratio', 'vol_spike', 'price', 'price_change_1m']
            
            # [NEW] Enhanced Columns
            cols = ['korean_name', 'market', 'score', 'slope', 'rsi', 'vol_ratio', 'channel_pos']
            
            # Filter cols that exist
            cols = [c for c in cols if c in df_scan.columns]
            
            # Rename for display
            display_df = df_scan[cols].rename(columns={
                'korean_name': 'Name',
                'market': 'Market', 
                'score': 'Score', 
                'slope': 'Slope(%)', 
                'rsi': 'RSI', 
                'vol_ratio': 'Vol Ratio', 
                'channel_pos': 'Channel'
            })
            
            st.dataframe(display_df, use_container_width=True)
            
            st.caption("💡 Tip: 점수와 기울기는 봇의 진입 판단 기준입니다. 설정에서 최소 기준을 변경할 수 있습니다.")
        else:
            st.info("조건에 맞는 종목이 없습니다.")

    with tab3:
        st.subheader("자산 현황 (Assets)")
        try:
            # Use cached function to prevent API bottleneck on every rerun
            df_bal, pie_data, total_krw = load_balances_cached()
            
            if df_bal is not None and not df_bal.empty:
                st.metric("Total Asset Value (Est.)", f"{total_krw:,.0f} KRW")
                
                c1, c2 = st.columns(2)
                c1.dataframe(df_bal[['currency', 'balance', 'avg_buy_price']], use_container_width=True)
                
                df_pie = pd.DataFrame(pie_data)
                c2.write("Asset Allocation")
                if not df_pie.empty:
                    st.bar_chart(df_pie.set_index("Currency"))
            else:
                 st.info("No assets found or API error.")
                 
        except Exception as e:
            st.error(f"Error fetching balances: {e}")



    with tab4:

        st.subheader("Daily History")
        
        if isinstance(history, list) and history:
            # Date Input (Default: Today)
            today = datetime.date.today()
            col_d1, col_d2 = st.columns([1, 2])
            
            with col_d1:
                selected_date = st.date_input(
                    "📅 날짜 선택 (Period Selection)", 
                    (today, today),
                    format="YYYY-MM-DD"
                )
            
            # Call Cached Processor
            trade_amt_default = float(config.get("TRADE_AMOUNT", 10000))
            df_processed = process_history_data(history, trade_amt_default)
            
            if not df_processed.empty:
                # Filter Logic (Fast filtering on processed DF)
                if 'date_dt' in df_processed.columns:
                    if isinstance(selected_date, tuple):
                        if len(selected_date) == 2:
                            start, end = selected_date
                            mask = (df_processed['date_dt'] >= start) & (df_processed['date_dt'] <= end)
                            date_label = f"{start} ~ {end}"
                        elif len(selected_date) == 1:
                            start = selected_date[0]
                            mask = df_processed['date_dt'] == start
                            date_label = f"{start}"
                        else:
                            mask = pd.Series([True] * len(df_processed))
                            date_label = "All Time"
                    else:
                        mask = df_processed['date_dt'] == selected_date
                        date_label = f"{selected_date}"
                        
                    df_filtered = df_processed.loc[mask]
                else:
                    df_filtered = df_processed
                    date_label = "Total"

                # Aggregated Stats
                total_pnl = df_filtered['pnl'].sum()
                total_trades = len(df_filtered)
                wins = len(df_filtered[df_filtered['pnl'] > 0])
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

                st.markdown(f"### 📈 수익 요약 ({date_label})")
                col_s1, col_s2, col_s3 = st.columns(3)
                col_s1.metric("총 손익 (Net PnL)", f"{total_pnl:,.0f} KRW", delta_color="normal")
                col_s2.metric("총 거래 횟수", f"{total_trades}회")
                col_s3.metric("승률 (Win Rate)", f"{win_rate:.1f}%")
                
                st.divider()

                # Display Table
                display_cols = ['time', 'market', 'Analysis', 'Return (%)', 'reason', 'Buy Price', 'Sell Price']
                # Renaissance cols if needed (processed df already has formatting)
                df_final = df_filtered.rename(columns={
                    'time': 'Time', 'market': 'Market', 'reason': 'Reason'
                })
                # Check column existence before select
                final_cols = [c for c in ['Time', 'Market', 'Analysis', 'Return (%)', 'Reason', 'Buy Price', 'Sell Price'] if c in df_final.columns]
                
                st.dataframe(df_final[final_cols].sort_values('Time', ascending=False), use_container_width=True)
            else:
                st.info("No processed data available.")
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
