import pyupbit
import time
import json
import os
import datetime
import logging
from logging.handlers import TimedRotatingFileHandler
from myupbit01 import trend

STATE_FILE = "trade_state.json"
HISTORY_FILE = "trade_history.json"
CONFIG_FILE = "trader_config.json"
COMMAND_FILE = "command.json"
SCAN_RESULTS_FILE = "scan_results.json"
LOG_DIR = "logs"

class AutoTrader:
    def __init__(self):
        self.setup_logging()
        self.access_key = os.getenv("UPBIT_ACCESS_KEY")
        self.secret_key = os.getenv("UPBIT_SECRET_KEY")
        if not self.access_key or not self.secret_key:
            self.log("CRITICAL ERROR: API Keys are missing in .env file.")
            print("Please set UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY in .env")
            import sys; sys.exit(1)
            
        self.upbit = pyupbit.Upbit(self.access_key, self.secret_key)
        
        # Load constraints
        self.config = {
            "TRADE_AMOUNT": float(os.getenv("TRADE_AMOUNT", 10000)),
            "MAX_SLOTS": int(os.getenv("MAX_SLOTS", 3)),
            "COOLDOWN_MINUTES": int(os.getenv("COOLDOWN_MINUTES", 60)),
            "PROFIT_TARGET": 0.005,
            "STOP_LOSS": -0.02,
            "TRAILING_STOP_CALLBACK": 0.002
        }
        self.load_config()
        
        self.state = self.load_state()
        self.last_summary_date = datetime.date.today()
        self.last_config_check = 0
        self.is_active = True # Master switch

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    new_config = json.load(f)
                    # Update config with new values, keeping defaults if key missing
                    self.config.update(new_config)
            except Exception as e:
                self.log(f"Error loading config: {e}")
                
        # Update convenient attributes
        self.trade_amount = float(self.config.get("TRADE_AMOUNT", 10000))
        self.max_slots = int(self.config.get("MAX_SLOTS", 3))
        self.cooldown_minutes = int(self.config.get("COOLDOWN_MINUTES", 60))

    def load_state(self):
        state = {"slots": [], "cooldowns": {}}
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Migration: If old format (single dict with 'status'), convert to slot
                    if "status" in loaded and "slots" not in loaded:
                        self.log("Migrating single state to multi-slot state...")
                        state['slots'].append(loaded)
                        self.state = state # temporarily set for save
                        self.save_state() # Save immediately
                    elif "slots" in loaded:
                        state = loaded
                        if "cooldowns" not in state:
                            state["cooldowns"] = {}
            except Exception as e:
                self.log(f"Error loading state: {e}")
        return state

    def save_state(self):
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=4, ensure_ascii=False)

    def setup_logging(self):
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
            
        self.logger = logging.getLogger("AutoTrader")
        self.logger.setLevel(logging.INFO)
        
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
        
        self.logger.addHandler(handler)
        
        # Also log to console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def log(self, msg):
        self.logger.info(msg)

    def get_tick_size(self, price):
        if price >= 2000000: return 1000
        if price >= 1000000: return 500
        if price >= 500000: return 100
        if price >= 100000: return 50
        if price >= 10000: return 10
        if price >= 1000: return 5
        if price >= 100: return 1
        if price >= 10: return 0.1
        return 0.01

    def get_best_target(self):
        # Scan strictly aligned coins
        candidates = trend.get_candidates()
        strict_coins = trend.scan_trends(candidates, strict_slope=True)
        
        if not strict_coins:
            return None
            
        # Sort by lowest disparity (SMA5/SMA20)
        # disparity_5_20 is percentage, smaller is better (closer to moving average support)
        strict_coins.sort(key=lambda x: x['disparity_5_20'])
        
        return strict_coins[0] # Return the best one

    def reset_state(self):
        self.state = {"slots": [], "cooldowns": {}}
        self.save_state()

    def check_market_condition(self):
        try:
            btc_candle = pyupbit.get_ohlcv("KRW-BTC", interval="minute1", count=1)
            if btc_candle is not None:
                open_p = btc_candle['open'].iloc[-1]
                close_p = btc_candle['close'].iloc[-1]
                btc_change = (close_p - open_p) / open_p
                
                if btc_change <= -0.007:
                    print(f"MARKET SWITCH: BTC is crashing ({btc_change*100:.2f}%). Pause scanning.")
                    return False
        except Exception as e:
            print(f"Error checking market condition: {e}")
        return True

    def sync_slots_with_balances(self):
        try:
            balances = self.upbit.get_balances()
            current_slot_markets = [s['market'] for s in self.state['slots']]
            
            for b in balances:
                currency = b['currency']
                if currency in ["KRW", "USDT", "XAUT"]: continue
                
                market = f"KRW-{currency}"
                balance = float(b['balance'])
                avg_buy_price = float(b['avg_buy_price'])
                
                # Minimum value check (e.g. > 5000 KRW) to ignore dust
                if balance * avg_buy_price < 5000: continue
                
                if market not in current_slot_markets:
                    self.log(f"RECOVERY: Found orphan coin {market} in balance. Adding to slots.")
                    
                    curr_price = pyupbit.get_current_price(market)
                    
                    new_slot = {
                        "status": "HOLDING",
                        "market": market,
                        "buy_order_uuid": "recovered",
                        "order_price": avg_buy_price,
                        "avg_buy_price": avg_buy_price,
                        "order_time": datetime.datetime.now().isoformat(),
                        "entry_time": datetime.datetime.now().isoformat(),
                        "highest_price": curr_price if curr_price else avg_buy_price,
                        "add_buy_done": False
                    }
                    self.state['slots'].append(new_slot)
                    current_slot_markets.append(market)
            
            self.save_state()
        except Exception as e:
            self.log(f"Error syncing balances: {e}")

    def run(self):
        self.log(f"AutoTrader started. Max Slots: {self.max_slots}")
        self.sync_slots_with_balances()
        while True:
            try:
                # Reload config every 5 seconds
                now = time.time()
                if now - self.last_config_check > 5:
                    self.load_config()
                    self.process_commands() # Check for commands
                    self.last_config_check = now

                # Check daily summary
                self.check_daily_summary()
                
                # Clean expired cooldowns
                self.clean_cooldowns()
                
                # Check Market Condition (Circuit Breaker)
                is_market_good = self.check_market_condition()
                
                # 1. Process existing slots
                # We iterate a copy to verify/modify safely if needed, though direct access is fine if we don't delete mid-loop
                # Better approach: Iterate index or copy.
                active_slots = self.state.get("slots", [])
                
                # Filter out empty or finished slots (though we usually remove them immediately)
                # Let's iterate and process
                for i, slot in enumerate(active_slots):
                    self.process_slot(slot, i)
                
                # Remove finished slots (marked for removal)
                # We can mark slots with 'status': 'DONE' or remove them inside process_slot but modifying list while iterating is bad.
                # Let's look for slots to remove
                self.state['slots'] = [s for s in active_slots if s.get('status') != 'DONE']
                if len(self.state['slots']) != len(active_slots):
                    self.save_state()
                
                # 2. Search for new target (Always scan for dashboard, buy only if slots open)
                if is_market_good:
                    self.try_search_and_enter()
                    
                time.sleep(1)
            except Exception as e:
                self.log(f"Error in main loop: {e}")
                time.sleep(5)

    def save_scan_results(self, candidates):
        try:
            with open(SCAN_RESULTS_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "candidates": candidates
                }, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log(f"Error saving scan results: {e}")

    def try_search_and_enter(self):
        # Throttle search to avoid spamming API if no target found
        now = time.time()
        last_search = self.state.get('last_search_time', 0)
        # Scan every 30 seconds if full, or 10 seconds if empty? Let's keep 20s default for now
        if now - last_search < 20: 
            return

        self.state['last_search_time'] = now
        
        self.log("Searching for new target...")
        
        min_volatility = float(self.config.get("MIN_VOLATILITY", 0.01))
        candidates = trend.get_candidates(min_volatility=min_volatility)
        
        # Scored scanning
        scored_coins = trend.scan_trends(candidates, config=self.config)
        
        # Save results for UI
        self.save_scan_results(scored_coins)
        
        # [NEW] Save history for analysis (Only Top Candidates)
        trend.save_scan_history(scored_coins, filename=os.path.join(LOG_DIR, "scan_history.csv"))
        
        # STOP here if slots are full
        if len(self.state.get('slots',[])) >= self.max_slots:
            return

        # Filter out held markets and cooldown markets
        held_markets = [s['market'] for s in self.state['slots'] if 'market' in s]
        cooldown_markets = self.state.get('cooldowns', {}).keys()
        
        # Filter out held markets and cooldown markets
        available_coins = [c for c in scored_coins if c['market'] not in held_markets and c['market'] not in cooldown_markets]
        
        if not available_coins:
            self.log("No new target found.")
            return

        # Sort by score (descending)
        # scan_trends already returns sorted by score, but re-sort to be sure
        available_coins.sort(key=lambda x: x['score'], reverse=True)
        
        target = available_coins[0]
        market = target['market']
        score = target['score']
        
        # Minimum Score Threshold (Configurable, Default 30)
        # 20 was too low (allowing weak trends).
        min_score = float(self.config.get("MIN_ENTRY_SCORE", 30))
        if score < min_score:
             self.log(f"Best target {market} score ({score}) is too low (min {min_score}). Skipping.")
             return

        self.log(f"Target found: {target['korean_name']} ({market}) Score: {score}")
        
        # [MODIFIED] Use Market Order for immediate execution
        # Removed tick size calculation and limit order logic
        
        # Place market buy order
        ret = self.upbit.buy_market_order(market, self.trade_amount)
        if ret and 'uuid' in ret:
            new_slot = {
                "status": "BUY_ORDER_WAITING",
                "market": market,
                "buy_order_uuid": ret['uuid'],
                "order_price": 0, # Will be updated after filling
                "order_time": datetime.datetime.now().isoformat()
            }
            self.state['slots'].append(new_slot)
            self.save_state()
            self.log(f"Market buy order placed for {market}. Slot occupied.")
        else:
            self.log(f"Failed to place order for {market}: {ret}")

    def process_slot(self, slot, index):
        status = slot.get("status")
        if status == "BUY_ORDER_WAITING":
            self.step_buy_order_waiting(slot)
        elif status == "HOLDING":
            self.step_holding(slot)

    def remove_slot(self, slot):
        # Add to cooldown (1 hour)
        market = slot['market']
        if 'cooldowns' not in self.state:
            self.state['cooldowns'] = {}
            
        release_time = datetime.datetime.now() + datetime.timedelta(minutes=self.cooldown_minutes)
        self.state['cooldowns'][market] = release_time.isoformat()
        self.log(f"Cooldown set for {market} until {release_time.strftime('%H:%M:%S')}")
        
        # Mark for removal
        slot['status'] = 'DONE'
        # Actual removal happens in main loop
        
    def clean_cooldowns(self):
        if 'cooldowns' not in self.state:
            return
            
        now = datetime.datetime.now()
        to_remove = []
        for market, time_str in self.state['cooldowns'].items():
            release_time = datetime.datetime.fromisoformat(time_str)
            if now >= release_time:
                to_remove.append(market)
                
        if to_remove:
            for m in to_remove:
                del self.state['cooldowns'][m]
                self.log(f"Cooldown expired for {m}")
            self.save_state()

    def save_trade_history(self, market, buy_price, sell_price, reason, pnl, profit_rate):
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except:
                pass
                
        record = {
            "date": datetime.date.today().isoformat(),
            "time": datetime.datetime.now().isoformat(),
            "market": market,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "reason": reason,
            "pnl": pnl,
            "profit_rate": profit_rate
        }
        history.append(record)
        
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4, ensure_ascii=False)

    def check_daily_summary(self):
        today = datetime.date.today()
        if today != self.last_summary_date:
            # Daily summary calculation
            self.log(f"=== Daily Summary for {self.last_summary_date} ===")
            
            history = []
            if os.path.exists(HISTORY_FILE):
                try:
                    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                except:
                    pass
            
            # Filter yesterday/last summary date trades
            target_date_str = self.last_summary_date.isoformat()
            daily_trades = [h for h in history if h['date'] == target_date_str]
            
            if daily_trades:
                total_pnl = sum(h['pnl'] for h in daily_trades)
                wins = len([h for h in daily_trades if h['pnl'] > 0])
                total = len(daily_trades)
                win_rate = (wins / total) * 100 if total > 0 else 0
                
                self.log(f"Total Trades: {total}")
                self.log(f"Wins: {wins} ({win_rate:.2f}%)")
                self.log(f"Total PnL: {total_pnl:,.0f} KRW")
            else:
                self.log("No trades recorded.")
                
            self.last_summary_date = today

    def step_buy_order_waiting(self, slot):
        # Check order status (timeout 5 mins)
        market = slot['market']
        uuid = slot['buy_order_uuid']
        order_time = datetime.datetime.fromisoformat(slot['order_time'])
        
        # Timeout check
        elapsed = (datetime.datetime.now() - order_time).total_seconds()
        if elapsed > 300: # 5 minutes
            self.log(f"Buy order timed out for {market}. Canceling...")
            self.upbit.cancel_order(uuid)
            time.sleep(2) # Wait for cancel
            self.remove_slot(slot)
            return
            
        print(f"Slot {market}: Waiting for buy order to fill... ({int(elapsed)}s elapsed)")
        
        # Check execution
        try:
            order = self.upbit.get_order(uuid)
            if order and order['state'] == 'done':
                self.log(f"Buy order filled! {market} at {slot['order_price']}")
                
                slot['status'] = "HOLDING"
                slot['avg_buy_price'] = slot['order_price'] # Approx
                slot['entry_time'] = datetime.datetime.now().isoformat()
                slot['highest_price'] = slot['order_price']
                slot['add_buy_done'] = False
                self.save_state()
            elif order and order['state'] == 'cancel':
                # Check if any amount was actually filled despite cancel
                executed_vol = float(order.get('executed_volume', 0))
                if executed_vol > 0:
                    self.log(f"Order {market} canceled but partially filled ({executed_vol}). Treating as success.")
                    slot['status'] = "HOLDING"
                    # We might not know exact price, so fetch from balance
                    time.sleep(1) 
                    self.update_avg_price(slot)
                    slot['entry_time'] = datetime.datetime.now().isoformat()
                    # Initialize highest_price with current price or avg price
                    slot['highest_price'] = slot['avg_buy_price']
                    slot['add_buy_done'] = False
                    self.save_state()
                else: 
                    self.log(f"Order for {market} canceled externally (0 fill).")
                    self.remove_slot(slot)
        except Exception as e:
            self.log(f"Error checking order {market}: {e}")

    def step_holding(self, slot):
        market = slot['market']
        avg_price = float(slot['avg_buy_price'])
        
        curr_price = pyupbit.get_current_price(market)
        if not curr_price: return

        # Update highest price tracking for trailing stop
        if curr_price > slot.get('highest_price', 0):
            slot['highest_price'] = curr_price
            self.save_state() # Save for persistence
        
        highest_price = slot['highest_price']
        profit_rate = (curr_price - avg_price) / avg_price
        
        print(f"Slot {market}: {curr_price}, Avg: {avg_price:.0f}, Ret: {profit_rate*100:.2f}%")
        
        # Settings from config
        stop_loss = self.config.get("STOP_LOSS", -0.02)
        profit_target = self.config.get("PROFIT_TARGET", 0.005)
        trailing_callback = self.config.get("TRAILING_STOP_CALLBACK", 0.002)

        # 1. Defense Strategy
        # 1-1. Sudden Drop (5min candle -1%)
        # Check only once per minute to save API calls
        now = time.time()
        last_check = slot.get('last_candle_check', 0)
        
        if now - last_check >= 60:
            df = pyupbit.get_ohlcv(market, interval="minute5", count=1)
            slot['last_candle_check'] = now
            
            if df is not None:
                 open_price = df.iloc[-1]['open']
                 cur_change_from_open = (curr_price - open_price) / open_price
                 if cur_change_from_open <= -0.01:
                     self.log(f"DEFENSE: Sudden drop detected for {market} ({cur_change_from_open*100:.2f}%). Selling...")
                     self.sell_market(slot, "Sudden Drop", profit_rate)
                     return

        # 1-2. Stop Loss
        if profit_rate <= stop_loss:
            self.log(f"DEFENSE: Stop loss triggered for {market} ({profit_rate*100:.2f}%). Selling...")
            self.sell_market(slot, "Stop Loss", profit_rate)
            return

        # 2. Add-buy Strategy (Refined)
        entry_time = datetime.datetime.fromisoformat(slot['entry_time'])
        elapsed_mins = (datetime.datetime.now() - entry_time).total_seconds() / 60
        
        # New Config Params
        add_buy_wait = int(self.config.get("ADD_BUY_WAIT_MINUTES", 15)) # Default 15 mins
        add_buy_threshold = float(self.config.get("ADD_BUY_THRESHOLD", -0.015)) # Default -1.5%
        add_buy_min_score = float(self.config.get("ADD_BUY_MIN_SCORE", 20.0)) # Default Score 20
        
        if elapsed_mins >= add_buy_wait and profit_rate <= add_buy_threshold and not slot.get('add_buy_done', False):
             # [Re-check Score] Is this coin still valid?
             t_data = trend.analyze_trend(market, 
                                          vol_spike_ratio=float(self.config.get("VOL_SPIKE_RATIO", 3.0)),
                                          rsi_threshold=float(self.config.get("RSI_THRESHOLD", 70.0)))
             
             if t_data:
                 # Calculate score
                 ts_score, _ = trend.analyze_trade_strength(market, buying_power_threshold=float(self.config.get("BUYING_POWER_THRESHOLD", 0.55)))
                 current_score = trend.calculate_score(t_data, ts_score, self.config)
                 
                 self.log(f"EXIT STRATEGY Check: {market} fell to {profit_rate*100:.2f}%. Current Score: {current_score}")
                 
                 if current_score >= add_buy_min_score:
                    self.log(f"-> COND MET: Score {current_score} >= {add_buy_min_score}. Executing Add-buy...")
                    ret = self.upbit.buy_market_order(market, self.trade_amount)
                    if ret and 'uuid' in ret:
                        time.sleep(2)
                        self.update_avg_price(slot)
                        slot['add_buy_done'] = True
                        slot['highest_price'] = curr_price 
                        self.save_state()
                        self.log(f"Add-buy complete for {market}.")
                    else:
                        self.log(f"Add-buy failed for {market}: {ret}")
                 else:
                     self.log(f"-> STOP: Score {current_score} < {add_buy_min_score}. Skip Add-buy.")
             else:
                 self.log(f"-> STOP: Trend analysis failed for {market}. Skip Add-buy.")
        

        # 3. Take Profit (Trailing Stop)
        # Active only if max profit reached target
        max_profit_rate = (highest_price - avg_price) / avg_price
        
        if max_profit_rate >= profit_target:
            # Drop from highest
            drop_rate = (highest_price - curr_price) / highest_price
            if drop_rate >= trailing_callback: 
                self.log(f"PROFIT: Trailing stop triggered for {market}. High: {highest_price}, Curr: {curr_price}. Selling...")
                self.sell_market(slot, "Trailing Stop", profit_rate)
                return

    def sell_market(self, slot, reason, profit_rate):
        market = slot['market']
        # Fetch balance to sell all
        balance = self.upbit.get_balance(market)
        if balance > 0:
            avg_buy_price = float(slot['avg_buy_price'])
            
            # Simple PnL calculation assumption (balance * (current_price - avg_buy_price))
            current_price = pyupbit.get_current_price(market)
            pnl = (current_price - avg_buy_price) * balance
            
            self.upbit.sell_market_order(market, balance)
            self.log(f"Sell order executed for {market}. Reason: {reason}, PnL: {pnl:.0f} KRW ({profit_rate*100:.2f}%)")
            
            # Save history
            self.save_trade_history(market, avg_buy_price, current_price, reason, pnl, profit_rate)
            
            time.sleep(2)
            self.remove_slot(slot)
        else:
            self.log(f"No balance to sell for {market}?")
            self.remove_slot(slot)

    def process_commands(self):
        if os.path.exists(COMMAND_FILE):
            try:
                with open(COMMAND_FILE, 'r', encoding='utf-8') as f:
                    cmd_data = json.load(f)
                
                # Process command 
                if cmd_data:
                    cmd_type = cmd_data.get('command')
                    
                    if cmd_type == 'panic_sell':
                        market = cmd_data.get('market')
                        self.log(f"COMMAND: Panic Sell received for {market}")
                        # Find slot
                        slots = self.state.get('slots', [])
                        target_slot = next((s for s in slots if s['market'] == market), None)
                        if target_slot:
                             self.sell_market(target_slot, "Panic Sell (Command)", 0.0)
                        else:
                            self.log(f"COMMAND FAILED: Slot not found for {market}")
                            
                    elif cmd_type == 'master_stop':
                        self.log("COMMAND: Master Stop executed. New entries paused.")
                        self.is_active = False
                        
                    elif cmd_type == 'master_start':
                        self.log("COMMAND: Master Start executed. Resuming.")
                        self.is_active = True
                
                # Clear command file
                os.remove(COMMAND_FILE)
            except Exception as e:
                self.log(f"Error processing command: {e}")

    def update_avg_price(self, slot):
        market = slot['market']
        # Fetch actual average price from account
        balances = self.upbit.get_balances()
        for b in balances:
            if b['currency'] == market.split('-')[1] and b['unit_currency'] == market.split('-')[0]:
                slot['avg_buy_price'] = float(b['avg_buy_price'])
                return
    
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    trader = AutoTrader()
    trader.run()
