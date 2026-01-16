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
            st.subheader("전략 설정")
            min_entry_score = st.number_input("최소 진입 점수", value=int(config.get("MIN_ENTRY_SCORE", 30)))
            
            # Exit Strategy
            exit_strategies = config.get("exit_strategies", {})
            st.divider()
            st.subheader("청산 전략 (고급)")
            stop_loss = st.slider("손절 기준 (%)", -10.0, -0.1, float(exit_strategies.get("stop_loss", 0.02)) * -100) / -100
            trailing_trigger = st.slider("트레일링 시작 (%)", 0.1, 5.0, float(exit_strategies.get("trailing_stop_trigger", 0.005)) * 100) / 100
            trailing_gap = st.slider("트레일링 감지 폭 (%)", 0.1, 2.0, float(exit_strategies.get("trailing_stop_gap", 0.002)) * 100) / 100
            
            if st.form_submit_button("설정 업데이트"):
                # Preserve existing structure
                config["TRADE_AMOUNT"] = trade_amount
                config["MAX_SLOTS"] = max_slots
                config["COOLDOWN_MINUTES"] = cooldown
                config["MIN_ENTRY_SCORE"] = min_entry_score
                
                # Update nested exit strategies
                if "exit_strategies" not in config: config["exit_strategies"] = {}
                config["exit_strategies"]["stop_loss"] = abs(stop_loss)
                config["exit_strategies"]["trailing_stop_trigger"] = trailing_trigger
                config["exit_strategies"]["trailing_stop_gap"] = trailing_gap
                
                save_json(CONFIG_FILE, config)
                st.success("설정이 업데이트 되었습니다!")

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
            for slot in slots:
                market = slot.get('market')
                status = slot.get('status')
                avg_price = slot.get('avg_buy_price', 0)
                
                # Fetch current info
                try:
                    current_price = pyupbit.get_current_price(market) or 0
                except Exception:
                    current_price = 0
                
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
                
                # Calculate Profit & Trailing Info
                entry_price = float(slot.get('avg_buy_price', 0))
                highest_price = float(slot.get('highest_price', entry_price)) # Need to ensure trader saves this
                profit_rate = 0.0
                
                if entry_price > 0 and current_price > 0:
                    profit_rate = (current_price - entry_price) / entry_price
                    
                # Trailing Check
                profit_target = float(config.get("PROFIT_TARGET", 0.005))
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
                    c_head1, c_head2 = st.columns([3, 1])
                    
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
                    '>{status_kr}</span>
                    """
                    
                    title_md = f"**{market}** {badge_html}"
                    if is_trailing_active:
                        title_md += " 🔥 **익절 감시 중 (Trailing)**"
                    c_head1.markdown(title_md, unsafe_allow_html=True)
                    
                    if status == "BUY_WAIT":
                         if c_head2.button("🚫 취소 (Cancel)", key=f"cancel_{market}"):
                             send_command("cancel_buy_order", market=market)
                    else:
                        if c_head2.button("🚨 긴급 매도 (Panic)", key=f"panic_{market}"):
                            send_command("panic_sell", market=market)

                    c1, c2, c3, c4 = st.columns(4)
                    
                    # Entry Price vs Limit Price Logic
                    display_price_label = "매수가 (Entry)"
                    display_price_val = entry_price
                    
                    display_amt_label = "평가금액 (Value)"
                    display_amt_val = invested_amount
                    
                    if status == "BUY_WAIT":
                        display_price_label = "주문가 (Limit)"
                        # Fallback to entry_price if limit_price missing, though it should be there
                        display_price_val = float(slot.get('limit_price', entry_price))
                        
                        display_amt_label = "주문총액 (Order)"
                        # Show configured TRADE_AMOUNT for pending buys
                        display_amt_val = float(config.get("TRADE_AMOUNT", 10000))
                    elif status == "HOLDING":
                        # [NEW] Show Sell Limit Price if available
                        if slot.get('sell_limit_price'):
                            display_price_label = "매도예약 (Sell)"
                            display_price_val = float(slot['sell_limit_price'])

                    c1.metric("수익률 (Return)", f"{profit_rate*100:.2f}%", f"{current_value - invested_amount:,.0f} KRW")
                    c2.metric("현재가 (Price)", f"{current_price:,.4f}", f"고점: {highest_price:,.4f}")
                    c3.metric(display_price_label, f"{display_price_val:,.4f}")
                    c4.metric(display_amt_label, f"{display_amt_val:,.0f} KRW")
                    
                    if is_trailing_active:
                        st.progress(min(max_profit_rate / (profit_target * 2), 1.0), text=f"최고 수익률: {max_profit_rate*100:.2f}% (목표: {profit_target*100:.2f}%)")

        st.subheader("재진입 대기 (Cooldowns)")
        st.write(state.get("cooldowns", {}))

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
            cols = ['korean_name', 'score', 'rsi', 'buy_ratio', 'vol_spike', 'price', 'price_change_1m']
            # Filter cols that exist
            cols = [c for c in cols if c in df_scan.columns]
            
            st.dataframe(df_scan[cols], use_container_width=True)
            
            st.caption("점수 가이드: 볼륨급등(20) + 추세강도(10) + 매수체결강도(10) + RSI(5) + 이동평균(5)")
        else:
            st.info("조건에 맞는 종목이 없습니다.")

    with tab3:
        st.subheader("자산 현황 (Assets)")
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
            
            # [NEW] Date Filtering
            # Ensure date column is datetime or comparable string. 'date' is YYYY-MM-DD string.
            if 'date' in df_hist.columns:
                df_hist['date_dt'] = pd.to_datetime(df_hist['date']).dt.date
                
                # Date Input (Default: Today)
                today = datetime.date.today()
                col_d1, col_d2 = st.columns([1, 2])
                
                with col_d1:
                    # Single date or range? User asked for "Period or Date".
                    # Let's provide a mode selector or just a date input that accepts range.
                    # st.date_input with tuple logs range.
                    selected_date = st.date_input(
                        "📅 날짜 선택 (Period Selection)", 
                        (today, today), # Default range: Today only
                        format="YYYY-MM-DD"
                    )
                
                # Filter Logic
                if isinstance(selected_date, tuple):
                    if len(selected_date) == 2:
                        start_date, end_date = selected_date
                        mask = (df_hist['date_dt'] >= start_date) & (df_hist['date_dt'] <= end_date)
                        df_filtered = df_hist.loc[mask]
                        date_label = f"{start_date} ~ {end_date}"
                    elif len(selected_date) == 1:
                        start_date = selected_date[0]
                        mask = df_hist['date_dt'] == start_date
                        df_filtered = df_hist.loc[mask]
                        date_label = f"{start_date}"
                    else:
                        df_filtered = df_hist
                        date_label = "All Time"
                else:
                    # Single date
                    mask = df_hist['date_dt'] == selected_date
                    df_filtered = df_hist.loc[mask]
                    date_label = f"{selected_date}"
            else:
                df_filtered = df_hist
                date_label = "Total"

            # [NEW] Aggregated Stats (Filtered)
            # Fix: Calculate PnL if missing (Backward Compatibility)
            if 'pnl' not in df_filtered.columns:
                 # Estimate based on config TRADE_AMOUNT
                 trade_amt = float(config.get("TRADE_AMOUNT", 10000))
                 df_filtered['pnl'] = df_filtered['profit_rate'] * trade_amt

            total_pnl = df_filtered['pnl'].sum() if not df_filtered.empty else 0
            total_trades = len(df_filtered)
            wins = len(df_filtered[df_filtered['pnl'] > 0]) if not df_filtered.empty else 0
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

            # Display Stats
            st.markdown(f"### 📈 수익 요약 ({date_label})")
            col_s1, col_s2, col_s3 = st.columns(3)
            col_s1.metric("총 손익 (Net PnL)", f"{total_pnl:,.0f} KRW", delta_color="normal")
            col_s2.metric("총 거래 횟수", f"{total_trades}회")
            col_s3.metric("승률 (Win Rate)", f"{win_rate:.1f}%")
            
            st.divider()

            # Function to generate analysis comment
            def generate_analysis(row):
                reason = row.get('reason', '')
                pnl_rate = row.get('profit_rate', 0)
                
                if "Trailing Stop" in reason:
                    return "🟢 [성공] 목표 수익 도달 후 익절"
                elif "Stop Loss" in reason:
                    return "🔴 [손절] 손실 제한 매도 실행"
                elif "Sudden Drop" in reason:
                    return "🛡️ [방어] 급락 감지되어 긴급 매도"
                elif pnl_rate > 0:
                    return "🟢 [익절] 수익 실현"
                else:
                    return "⚪ [매도] 기타 사유"

            # Apply Value Additions
            if not df_filtered.empty:
                df_filtered = df_filtered.copy() # Avoid SettingWithCopyWarning
                df_filtered['Analysis'] = df_filtered.apply(generate_analysis, axis=1)
                
                # Fix: Calculate sell_price if missing
                if 'sell_price' not in df_filtered.columns:
                     df_filtered['sell_price'] = df_filtered['buy_price'] * (1 + df_filtered['profit_rate'])
                
                df_filtered['Return (%)'] = df_filtered['profit_rate'].apply(lambda x: f"{x*100:+.2f}%")
                df_filtered['PnL (KRW)'] = df_filtered['pnl'].apply(lambda x: f"{x:,.0f}")
                df_filtered['Sell Price'] = df_filtered['sell_price'].apply(lambda x: f"{x:,.0f}")
                df_filtered['Buy Price'] = df_filtered['buy_price'].apply(lambda x: f"{x:,.0f}")
                
                # Select and Rename Columns
                display_cols = ['time', 'market', 'Analysis', 'Return (%)', 'PnL (KRW)', 'reason', 'Sell Price', 'Buy Price']
                df_final = df_filtered[display_cols].rename(columns={
                    'time': 'Time', 'market': 'Market', 'reason': 'Reason'
                })
                
                st.dataframe(df_final.sort_values('Time', ascending=False), use_container_width=True)
            else:
                 st.info(f"No trades found for {date_label}.")
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
