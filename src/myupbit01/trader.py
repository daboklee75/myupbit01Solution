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
            import sys; sys.exit(1)
            
        self.upbit = pyupbit.Upbit(self.access_key, self.secret_key)
        
        # Initial config load
        self.config = {}
        self.load_config()
        
        self.state = self.load_state()
        self.last_summary_date = datetime.date.today()
        self.last_config_check = 0
        self.is_active = True 

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except Exception as e:
                self.log(f"Error loading config: {e}")
        
        # Defaults
        # Defaults - Prioritize Config > Env > Default
        self.trade_amount = float(self.config.get("TRADE_AMOUNT", os.getenv("TRADE_AMOUNT", 10000)))
        self.max_slots = int(self.config.get("MAX_SLOTS", os.getenv("MAX_SLOTS", 3)))
        self.cooldown_minutes = int(self.config.get("COOLDOWN_MINUTES", os.getenv("COOLDOWN_MINUTES", 60)))

    def load_state(self):
        state = {"slots": [], "cooldowns": {}}
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)
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
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def log(self, msg):
        self.logger.info(msg)

    def get_tick_size(self, price):
        """
        Upbit Tick Size Logic (Conservative & Robust)
        To avoid 'invalid_price_bid' errors like KRW-BCH (880k price, 100 theoretical tick, but 500 actual),
        we use coarser tick sizes in ambiguous ranges.
        
        >= 2,000,000       : 1,000
        >= 500,000         : 500    (Changed from >= 1,000,000. Safe b/c 500 is multiple of 100)
        >= 100,000         : 50     (Standard)
        >= 10,000          : 10     (Standard)
        >= 1,000           : 5      (Standard)
        >= 100             : 1      (Standard)
        >= 10              : 0.1    (Standard)
        < 10               : 0.01
        """
        if price >= 2000000: return 1000
        if price >= 500000: return 500  # Conservative: Covers 500k~1M range with 500 tick
        if price >= 100000: return 50
        if price >= 10000: return 10
        if price >= 1000: return 5
        if price >= 100: return 1
        if price >= 10: return 0.1
        if price >= 1: return 0.01
        if price >= 0.1: return 0.001
        if price >= 0.01: return 0.0001
        return 0.00001

    def sync_slots_with_balances(self):
        """
        Recover slots from Upbit balances if state was lost.
        """
        try:
            balances = self.upbit.get_balances()
            current_slot_markets = [s['market'] for s in self.state['slots']]
            
            for b in balances:
                currency = b['currency']
                if currency in ["KRW", "USDT", "XAUT"]: continue
                
                market = f"KRW-{currency}"
                balance = float(b['balance'])
                avg_buy_price = float(b['avg_buy_price'])
                
                # Ignore dust (< 5000 KRW)
                if balance * avg_buy_price < 5000: continue
                
                if market not in current_slot_markets:
                    self.log(f"RECOVERY: Found orphan coin {market} in balance. Adding to slots.")
                    
                    new_slot = {
                        "status": "HOLDING",
                        "market": market,
                        "buy_order_uuid": "recovered",
                        "avg_buy_price": avg_buy_price,
                        "entry_time": datetime.datetime.now().isoformat(),
                        "highest_price": avg_buy_price,
                        "sell_order_uuid": None, # We don't know the sell order
                        "trend_info": {} # Unknown
                    }
                    self.state['slots'].append(new_slot)
                    current_slot_markets.append(market)
            
            self.save_state()
        except Exception as e:
            self.log(f"Error syncing balances: {e}")

    # ============================================================
    # MAIN LOOP
    # ============================================================
    def run(self):
        self.log(f"AutoTrader 2.0 (Trend Limit) started. Max Slots: {self.max_slots}")
        self.sync_slots_with_balances()
        
        while True:
            try:
                # 1. Config & Command Refresh
                now = time.time()
                if now - self.last_config_check > 10:
                    self.load_config()
                    self.process_commands()
                    self.last_config_check = now

                # 2. Housekeeping
                self.check_daily_summary()
                self.clean_cooldowns()

                # 3. Process Slots
                active_slots = self.state.get("slots", [])
                
                # [Optimization] Batch fetch prices for all HOLDING slots to save API calls
                holding_markets = [s['market'] for s in active_slots if s.get('status') == 'HOLDING']
                curr_prices = {}
                if holding_markets:
                    try:
                        curr_prices = pyupbit.get_current_price(holding_markets)
                        # If single result, ensure it's a dict (pyupbit returns float for single, dict for list)
                        if len(holding_markets) == 1 and isinstance(curr_prices, float):
                             curr_prices = {holding_markets[0]: curr_prices}
                    except Exception as e:
                        self.log(f"Error fetching batch prices: {e}")

                for i, slot in enumerate(active_slots):
                    self.process_slot(slot, curr_prices)

                # Remove done slots
                self.state['slots'] = [s for s in active_slots if s.get('status') != 'DONE']
                if len(self.state['slots']) != len(active_slots):
                    self.save_state()

                # 4. Search & Enter
                if self.is_active:
                    # [NEW] Check Global Market Condition (BTC Filter)
                    if self.check_market_condition():
                         self.try_search_and_enter()
                    
                time.sleep(0.2) # Faster loop for 1s response check
                
            except Exception as e:
                self.log(f"Error in main loop: {e}")
                time.sleep(5)
    
    def check_market_condition(self):
        """
        Check if the general market (BTC) is safe to enter.
        Returns True if safe, False if unsafe.
        """
        market_filter_cfg = self.config.get("market_filter", {})
        if not market_filter_cfg.get("use_btc_filter", False):
            return True # Filter disabled

        try:
            btc_market = "KRW-BTC"
            
            # 1. Check 1H Drop
            # Get ticker (change rate is usually 24h, so we need OHLCV for 1h)
            # Fetch recent candles to check short-term drop
            df = pyupbit.get_ohlcv(btc_market, interval="minute60", count=2) 
            if df is not None:
                # Calculate change from previous close (or just use current candle open vs close if 1h candle)
                # Better: Check current price vs 1 hour ago price
                # But get_ohlcv(minute60) gives completed or partial? 
                # Let's use get_ohlcv("minute1", count=60) for slider window? Too heavy.
                # Simple Logic: Current Price vs Open of current 1H candle? No.
                # Simple Logic: Current Price vs Close of 1H ago.
                
                curr_price = pyupbit.get_current_price(btc_market)
                prev_close_1h = df['close'].iloc[-2] # Last completed candle close
                
                drop_rate = (curr_price - prev_close_1h) / prev_close_1h
                drop_threshold = market_filter_cfg.get("btc_1h_drop_threshold", -0.015)
                
                if drop_rate < drop_threshold:
                    self.log(f"📉 Market Unsafe: BTC 1H Drop {drop_rate*100:.2f}% < Threshold {drop_threshold*100:.2f}%")
                    return False

            # 2. Check 3H Slope (Trend)
            # Use trend.analyze_trend for BTC
            # It uses 15m candles * 12 = 3 Hours
            # We can re-use the trend module
            btc_trend = trend.analyze_trend(btc_market)
            if btc_trend:
                slope = btc_trend['slope']
                slope_threshold = market_filter_cfg.get("btc_3h_slope_threshold", -0.5)
                
                if slope < slope_threshold:
                    self.log(f"📉 Market Unsafe: BTC 3H Slope {slope:.2f}% < Threshold {slope_threshold:.2f}%")
                    return False
            
            return True
            
        except Exception as e:
            self.log(f"Error checking market condition: {e}")
            return True # Fail-safe: Allow if check fails? Or Block? Let's Allow to avoid freezing on API error.

    def try_search_and_enter(self):
        # Check Slot Availability
        if len(self.state.get('slots', [])) >= self.max_slots:
            return

        # Throttle Search (e.g. every 30s)
        now = time.time()
        last_search = self.state.get('last_search_time', 0)
        if now - last_search < 30:
            return

        self.state['last_search_time'] = now
        
        # 1. Get Ranked Targets (Multi-Target Logic)
        # [SCANNER CHANGE] Fetch ALL candidates for UI Display (No filtering)
        # We fetch up to 50 candidates, min_score 0, min_slope -100 (basically everything)
        all_targets = trend.get_ranked_targets(min_score=0, limit=50, min_slope=-100.0)
        
        # Save results for UI Scanner (Show ALL)
        self.save_scan_results(all_targets)
        
        # 2. Filter for Trading Entry
        min_score = int(self.config.get("MIN_ENTRY_SCORE", 15))
        min_slope = float(self.config.get("min_slope_threshold", 0.5))
        
        self.log(f"Filtering targets for entry (Min Score: {min_score}, Min Slope: {min_slope:.2f}%)...")
        
        ranked_targets = []
        if all_targets:
            ranked_targets = [
                t for t in all_targets 
                if t['score'] >= min_score and t['slope'] >= min_slope
            ]
        
        if not ranked_targets:
            # self.log("No valid target found after filtering.") 
            return

        # Loop through ranked targets
        best_target = None
        for cand in ranked_targets:
            market = cand['market']
            score = cand['score']
            
            # Filters: already holding or cooldown
            held_markets = [s['market'] for s in self.state['slots']]
            cooldowns = self.state.get('cooldowns', {})
            
            if market in held_markets or market in cooldowns:
                self.log(f"Target {market} (Score {score}) is held or in cooldown. Skipping.")
                continue # Try next rank
                
            # Found valid target
            best_target = cand
            break
            
        if not best_target:
            self.log("All valid purchase candidates are held or in cooldown.")
            return

        market = best_target['market']
        score = best_target['score']
        slope = best_target['slope']

        # Log selection
        self.log(f"Target Selected: {market} (Score: {score}, Slope: {slope:.2f}%)")
        
        # 3. Calculate Limit Price (Dynamic)
        current_price = best_target['price']
        
        # Get Offsets
        offsets = self.config.get("limit_offsets", {"strong": 0.003, "moderate": 0.010, "weak": 0.015})
        thresholds = self.config.get("slope_thresholds", {"strong": 2.0, "moderate": 0.5})
        
        offset = offsets['weak']
        if slope >= thresholds['strong']:
            offset = offsets['strong']
        elif slope >= thresholds['moderate']:
            offset = offsets['moderate']
            
        # Calculate raw limit price
        limit_price = current_price * (1 - offset)

        # Round to tick size
        tick_size = self.get_tick_size(limit_price)
        limit_price = tick_size * round(limit_price / tick_size)
        
        # [FIX] Cast to int if tick_size >= 1 to avoid sending "870700.0"
        if tick_size >= 1:
            limit_price = int(limit_price)
            
        self.log(f"Placing Limit Buy Order at {limit_price} (Current: {current_price}, Offset: -{offset*100:.2f}%)")
        
        # 3. Place Order
        # Check Balance
        krw_balance = self.upbit.get_balance("KRW")
        if krw_balance is None:
            self.log("CRITICAL: Failed to fetch KRW balance. Check API Keys or Network.")
            return

        if krw_balance < self.trade_amount:
            self.log(f"Insufficient KRW Balance: {krw_balance} < {self.trade_amount}")
            return

        # Calculate Volume
        volume = self.trade_amount / limit_price
        
        ret = self.upbit.buy_limit_order(market, limit_price, volume)
        if ret and 'uuid' in ret:
            new_slot = {
                "status": "BUY_WAIT",
                "market": market,
                "buy_order_uuid": ret['uuid'],
                "limit_price": limit_price,
                "order_time": datetime.datetime.now().isoformat(),
                "trend_info": best_target,
                "entry_cnt": 0
            }
            self.state['slots'].append(new_slot)
            self.save_state()
        else:
            self.log(f"Order placement failed: {ret}")

    def process_slot(self, slot, curr_prices=None):
        status = slot.get("status")
        
        if status == "BUY_WAIT":
            self.manage_buy_wait(slot)
        elif status == "HOLDING":
            market = slot.get('market')
            price = None
            if curr_prices and market in curr_prices:
                price = curr_prices[market]
            self.manage_holding(slot, curr_price=price)

    def manage_buy_wait(self, slot):
        market = slot['market']
        uuid = slot['buy_order_uuid']
        order_time = datetime.datetime.fromisoformat(slot['order_time'])
        
        # Timeout Check (15 mins)
        timeout_mins = self.config.get("timeout_minutes", 15)
        elapsed = (datetime.datetime.now() - order_time).total_seconds()
        
        if elapsed > (timeout_mins * 60):
            self.log(f"Buy order for {market} timed out ({timeout_mins}m). Canceling...")
            self.upbit.cancel_order(uuid)
            time.sleep(1)
            self.remove_slot(slot, cooldown=False) # remove instantly, no cooldown or short cooldown?
            # Ideally short cooldown to avoid immediate retry at same bad price
            return

        # Check Order State
        try:
            order = self.upbit.get_order(uuid)
            if not order: return
            
            state = order['state']
            if state == 'done':
                # Filled
                avg_price = float(order.get('trades', [{'price': slot['limit_price']}])[0]['price']) # Fallback
                # Better: executed_funds / executed_volume
                if float(order.get('executed_volume',0)) > 0:
                    executed_funds = float(order.get('executed_funds', 0))
                    if executed_funds > 0:
                        avg_price = executed_funds / float(order['executed_volume'])
                
                self.log(f"Buy Order Filled for {market} at {avg_price}")
                
                slot['status'] = "HOLDING"
                slot['avg_buy_price'] = avg_price
                slot['initial_buy_price'] = avg_price # [NEW] Store initial price
                slot['entry_time'] = datetime.datetime.now().isoformat()
                slot['entry_cnt'] = 1 # Initial Entry counted as 1
                slot['highest_price'] = avg_price
                slot['sell_order_uuid'] = None
                
                # IMMEDIATE ACTION: Place Sell Limit at 3H High
                self.place_profit_limit(slot)
                self.save_state()
            
            elif state == 'wait':
                 # Log progress if partially filled or just once in a while?
                 # To avoid spam, maybe only if changed? or use debug log.
                 # For now, let's log if executed_volume > 0
                 # executed_vol = float(order.get('executed_volume', 0))
                 # if executed_vol > 0:
                 #    self.log(f"Buy Order {market} Partial Fill: {executed_vol} volume executed.")
                 pass

                
            elif state == 'cancel':
                # External cancel or partial fill
                executed_vol = float(order.get('executed_volume', 0))
                if executed_vol > 0:
                    executed_funds = float(order.get('executed_funds', 0))
                    if executed_funds > 0:
                        avg_price = executed_funds / executed_vol
                    else:
                        avg_price = float(order.get('price', slot['limit_price'])) # Fallback
                    self.log(f"Order canceled but partially filled for {market}. Managing position.")
                    slot['status'] = "HOLDING"
                    slot['avg_buy_price'] = avg_price
                    slot['initial_buy_price'] = avg_price # [NEW]
                    slot['entry_time'] = datetime.datetime.now().isoformat()
                    slot['highest_price'] = avg_price
                    slot['sell_order_uuid'] = None
                    self.place_profit_limit(slot)
                    self.save_state()
                else:
                    self.log(f"Order canceled externally for {market}.")
                    self.remove_slot(slot, cooldown=False)
                    
        except Exception as e:
            self.log(f"Error checking buy order {market}: {e}")

    def place_profit_limit(self, slot):
        # Calculate Target Price (3H High)
        market = slot['market']
        high_3h = slot['trend_info'].get('high_3h')
        avg_price = slot['avg_buy_price']
        
        if not high_3h:
            # Fallback
            target_price = avg_price * 1.01
        else:
            # Apply Take Profit Ratio (e.g., 0.5 = 50% of the way to High)
            tp_ratio = self.config['exit_strategies'].get('take_profit_ratio', 1.0)
            target_price = avg_price + (high_3h - avg_price) * tp_ratio
            
            # Ensure Min Profit 1.0%
            if target_price <= avg_price * 1.01:
                target_price = avg_price * 1.01
            
        target_price = self.get_tick_size(target_price) * round(target_price / self.get_tick_size(target_price))
        
        # Fetch balance
        balance = self.upbit.get_balance(market)
        if balance > 0:
            ret = self.upbit.sell_limit_order(market, target_price, balance)
            if ret and 'uuid' in ret:
                slot['sell_order_uuid'] = ret['uuid']
                slot['sell_limit_price'] = target_price # [NEW] Save sell price
                self.log(f"Placed Take Profit Limit for {market} at {target_price}")
            else:
                self.log(f"Failed to place TP Limit for {market}: {ret}")

    def manage_holding(self, slot, curr_price=None):
        market = slot['market']
        if curr_price is None:
             curr_price = pyupbit.get_current_price(market)
             
        if not curr_price: return
        
        avg_price = slot['avg_buy_price']
        profit_rate = (curr_price - avg_price) / avg_price
        
        # Track Highest Price
        if curr_price > slot.get('highest_price', 0):
            slot['highest_price'] = curr_price
            
            # Check Break-even
            break_even_trigger = self.config['exit_strategies'].get('break_even_trigger', 0.007)
            if profit_rate >= break_even_trigger:
                 # Ensure we have a stop protected above entry
                 # Logic handled in Stop Loss section via dynamic SL? 
            # Let's check locally.
                 slot['is_break_even_active'] = True
                 
        self.save_state()
    
        # --- Add-Buy (Watering) Logic ---
        exit_cfg = self.config.get('exit_strategies', {})
        add_buy_trigger = exit_cfg.get('add_buy_trigger', -1.0) # Default disabled if not set (or very low)
        max_add_buys = exit_cfg.get('max_add_buys', 0)
        current_entry_cnt = slot.get('entry_cnt', 1)
        
        if max_add_buys > 0 and current_entry_cnt <= max_add_buys:
            # Check trigger
            if profit_rate <= add_buy_trigger:
                 # Trigger Add-Buy
                 self.log(f"Triggering Add-Buy for {market} (Current: {profit_rate*100:.2f}%, Count: {current_entry_cnt}/{max_add_buys})")
                 
                 # 1. Check Logic & Cancel Existing Sell Limit
                 if slot.get('sell_order_uuid'):
                     self.upbit.cancel_order(slot['sell_order_uuid'])
                     time.sleep(1) # Wait for cancel
                     
                 # 2. Buy Market
                 # 3. Check Balance (Dynamic Amount)
                 krw_balance = self.upbit.get_balance("KRW")
                 
                 # Buy amount based on ratio (default 1.0 = 100% of TRADE_AMOUNT)
                 ab_ratio = exit_cfg.get('add_buy_amount_ratio', 1.0)
                 buy_amount = self.trade_amount * ab_ratio
                 
                 # Verify min order amount (KRW 5000)
                 if buy_amount < 5000: buy_amount = 5000

                 if krw_balance >= buy_amount:
                     ret = self.upbit.buy_market_order(market, buy_amount)
                     if ret and 'uuid' in ret:
                         # 4. Update Slot
                         time.sleep(1) # Wait for fill
                         # Re-fetch average price and balance (total volume)
                         avg_price = self.upbit.get_avg_buy_price(market)
                         
                         # [NEW] Calculate Watering Price
                         water_price = 0
                         try:
                             order_info = self.upbit.get_order(ret['uuid'])
                             if order_info and 'trades' in order_info and len(order_info['trades']) > 0:
                                 # Weighted avg of filled trades
                                 total_v = sum([float(t.get('volume',0)) for t in order_info['trades']])
                                 total_f = sum([float(t.get('funds',0)) for t in order_info['trades']])
                                 if total_v > 0: water_price = total_f / total_v
                             elif order_info and 'price' in order_info: # Fallback
                                 water_price = float(order_info.get('price', 0) or 0)
                                 # If market order, price might be None, check executed fields
                                 if water_price == 0 and float(order_info.get('executed_volume',0)) > 0:
                                      water_price = float(order_info.get('executed_funds',0)) / float(order_info.get('executed_volume',1))
                         except Exception as e:
                             self.log(f"Error fetching water price: {e}")
                         
                         slot['water_buy_price'] = water_price
                         
                         slot['avg_buy_price'] = avg_price
                         slot['entry_cnt'] = current_entry_cnt + 1
                         slot['sell_order_uuid'] = None # Reset
                         
                         # [FIX] Reset highest_price to new avg_price to prevent premature trailing stop
                         slot['highest_price'] = avg_price
                         
                         self.log(f"Add-Buy Executed. New Avg Price: {avg_price}")
                         
                         # 5. Re-place Profit Limit
                         self.place_profit_limit(slot)
                         self.save_state()
                         return # Exit manage_holding to avoid selling immediately
                     else:
                         self.log(f"Add-Buy Failed: {ret}")
                 else:
                     self.log(f"Skipping Add-Buy: Insufficient Balance ({krw_balance} < {buy_amount})")

        # --- Exit Logic ---
        
        # 1. Check if SP Limit Filled
        if slot.get('sell_order_uuid'):
            try:
                order = self.upbit.get_order(slot['sell_order_uuid'])
                if order and order['state'] == 'done':
                    self.log(f"Take Profit Limit Executed for {market}. PnL: Approx {(curr_price - avg_price)/avg_price*100:.2f}%")
                    vol = float(order.get('executed_volume', 0))
                    self.record_trade(slot, "🟢 [성공] 목표 수익 도달 후 익절", profit_rate, volume=vol)
                    self.remove_slot(slot, cooldown=True)
                    return
            except Exception:
                pass

        # 2. Dynamic Conditions (Market Sell)
        should_sell = False
        reason = ""
        
        exit_cfg = self.config.get('exit_strategies', {})
        if not exit_cfg:
             self.log("Warning: exit_strategies not found in config. Using defaults.")
        
        # A. Stop Loss
        sl_rate = -exit_cfg.get('stop_loss', 0.05)
        
        # B. Break-even SL
        is_break_even = slot.get('is_break_even_active', False)
        if is_break_even:
            # If triggered break-even, SL becomes +0.05%
            sl_rate = exit_cfg.get('break_even_sl', 0.0005) 
            
        if profit_rate <= sl_rate:
            # Stop Loss Triggered
            
            # Apply Time Confirmation ONLY for True Stop Loss (Loss Cut), not Break-even
            if not is_break_even and sl_rate < 0:
                confirm_secs = exit_cfg.get('stop_loss_confirm_seconds', 0)
                if confirm_secs > 0:
                    # Increment Counter
                    current_cnt = slot.get('sl_confirm_count', 0) + 1
                    slot['sl_confirm_count'] = current_cnt
                    
                    if current_cnt >= confirm_secs:
                        should_sell = True
                        reason = f"🔴 [손절] 손절 기준 도달 (설정: {sl_rate*100:.2f}%, 유지 {confirm_secs}초)"
                        slot['sl_confirm_count'] = 0 # Reset
                    else:
                        self.log(f"Stop Loss Pending for {market}: {current_cnt}/{confirm_secs}s (Current: {profit_rate*100:.2f}%)")
                        should_sell = False # Wait more
                else:
                    should_sell = True
                    reason = f"🔴 [손절] 손절 기준 도달 (설정: {sl_rate*100:.2f}%)"
            else:
                # Instant Sell for Break-even or if config is 0
                should_sell = True
                reason = f"🟡 [본절] 본전 사수 (설정: {sl_rate*100:.2f}%)"
                
        else:
            # Price recovered checks
            if slot.get('sl_confirm_count', 0) > 0:
                 self.log(f"Stop Loss Reset for {market} (Recovered to {profit_rate*100:.2f}%)")
                 slot['sl_confirm_count'] = 0

        # C. Trailing Stop
        ts_trigger = exit_cfg.get('trailing_stop_trigger', 0.008)
        ts_gap = exit_cfg.get('trailing_stop_gap', 0.002)
        max_rate = (slot['highest_price'] - avg_price) / avg_price
        
        if max_rate >= ts_trigger:
            high_price = slot['highest_price']
            # Drop from high
            drop_rate = (high_price - curr_price) / high_price
            if drop_rate >= ts_gap:
                # Trailing Stop Triggered
                ts_confirm_secs = exit_cfg.get('trailing_stop_confirm_seconds', 0)

                # [Logic Change] If Add-Buy happened (entry_cnt > 1), DISABLE Trailing Stop
                # to prioritize the safer Limit Sell (Take Profit) exit.
                if slot.get('entry_cnt', 1) > 1:
                     # Just reset count and do NOT sell via TS
                     if slot.get('ts_confirm_count', 0) > 0:
                         slot['ts_confirm_count'] = 0
                     should_sell = False
                     # Optional: Log once? "Skipping TS for Add-Buy slot, waiting for TP Limit"
                elif ts_confirm_secs > 0:
                    # Increment Counter
                    current_ts_cnt = slot.get('ts_confirm_count', 0) + 1
                    slot['ts_confirm_count'] = current_ts_cnt
                    
                    if current_ts_cnt >= ts_confirm_secs:
                        should_sell = True
                        reason = f"🟢 [익절] 트레일링 스탑 (최고: {max_rate*100:.2f}%, 하락감지, 유지 {ts_confirm_secs}초)"
                        slot['ts_confirm_count'] = 0
                    else:
                        self.log(f"Trailing Stop Pending for {market}: {current_ts_cnt}/{ts_confirm_secs}s (Drop: {drop_rate*100:.2f}%)")
                        should_sell = False
                else:
                    should_sell = True
                    reason = f"🟢 [익절] 트레일링 스탑 (최고: {max_rate*100:.2f}%, 하락감지)"
            else:
                 # Reset count if price recovers
                 if slot.get('ts_confirm_count', 0) > 0:
                     self.log(f"Trailing Stop Reset for {market} (Recovered Drop: {drop_rate*100:.2f}%)")
                     slot['ts_confirm_count'] = 0

        if should_sell:
            # [Added] Append Add-Buy Info if applicable
            entry_cnt = slot.get('entry_cnt', 1)
            if entry_cnt > 1:
                reason += f" (물타기: {entry_cnt-1}회)"

            self.log(f"Triggering Market Sell for {market}. Reason: {reason}. Current: {profit_rate*100:.2f}%")
            
            # Cancel Profit Limit First
            if slot.get('sell_order_uuid'):
                self.upbit.cancel_order(slot['sell_order_uuid'])
                time.sleep(0.5)
            
            # Market Sell
            balance = self.upbit.get_balance(market)
            if balance > 0:
                ret = self.upbit.sell_market_order(market, balance)
                if ret and 'uuid' in ret:
                    self.record_trade(slot, reason, profit_rate, volume=balance)
                    self.remove_slot(slot, cooldown=True)
                else:
                    self.log(f"Sell failed: {ret}")
    def record_trade(self, slot, reason, profit_rate, volume=0.0):
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except: pass
            
        buy_price = slot['avg_buy_price']
        sell_price = buy_price * (1 + profit_rate)
        pnl = (sell_price - buy_price) * volume
        
        record = {
            "date": datetime.date.today().isoformat(),
            "time": datetime.datetime.now().isoformat(),
            "market": slot['market'],
            "buy_price": buy_price,
            "sell_price": sell_price,
            "pnl": pnl,
            "volume": volume,
            "reason": reason,
            "profit_rate": profit_rate
        }
        history.append(record)
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4, ensure_ascii=False)

    def remove_slot(self, slot, cooldown=True):
        market = slot['market']
        if cooldown:
            release_time = datetime.datetime.now() + datetime.timedelta(minutes=self.cooldown_minutes)
            self.state['cooldowns'][market] = release_time.isoformat()
            self.log(f"Cooldown set for {market} until {release_time.strftime('%H:%M')}")
        
        slot['status'] = 'DONE'

    def clean_cooldowns(self):
        if 'cooldowns' not in self.state: return
        now = datetime.datetime.now()
        to_remove = [m for m, t in self.state['cooldowns'].items() if now >= datetime.datetime.fromisoformat(t)]
        for m in to_remove:
            del self.state['cooldowns'][m]
            self.log(f"Cooldown expired for {m}")
        if to_remove: self.save_state()

    def check_daily_summary(self):
        # Implementation similar to previous logic, simplified
        pass

    def save_scan_results(self, candidates):
        try:
            with open(SCAN_RESULTS_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "candidates": candidates
                }, f, indent=4, ensure_ascii=False)
        except: pass

    def process_commands(self):
        if os.path.exists(COMMAND_FILE):
            try:
                with open(COMMAND_FILE, 'r', encoding='utf-8') as f:
                    cmd_data = json.load(f)
                
                if cmd_data:
                    cmd_type = cmd_data.get('command')
                    
                    if cmd_type == 'panic_sell':
                        market = cmd_data.get('market')
                        self.log(f"COMMAND: Panic Sell received for {market}")
                        active_slots = self.state.get('slots', [])
                        target_slot = next((s for s in active_slots if s['market'] == market), None)
                        if target_slot:
                             # Cancel existing order if any
                             if target_slot.get('sell_order_uuid'):
                                 self.upbit.cancel_order(target_slot['sell_order_uuid'])
                                 time.sleep(1) # Wait for cancel
                             
                             # Sell all balance
                             balance = self.upbit.get_balance(market)
                             if balance > 0:
                                 self.upbit.sell_market_order(market, balance)
                                 self.record_trade(target_slot, "Panic Sell (Command)", 0.0, volume=balance)
                             
                             self.remove_slot(target_slot, cooldown=True)
                             self.log(f"Panic Sell Executed for {market}")
                        else:
                            self.log(f"COMMAND FAILED: Slot not found for {market}")
                            
                    elif cmd_type == 'master_stop':
                        self.log("COMMAND: Master Stop executed. New entries paused.")
                        self.is_active = False
                        
                    elif cmd_type == 'master_start':
                        self.log("COMMAND: Master Start executed. Resuming.")
                        self.is_active = True
                        
                    elif cmd_type == 'cancel_buy_order':
                        market = cmd_data.get('market')
                        self.log(f"COMMAND: Cancel Buy Order received for {market}")
                        active_slots = self.state.get('slots', [])
                        target_slot = next((s for s in active_slots if s['market'] == market), None)
                        
                        if target_slot and target_slot['status'] == 'BUY_WAIT':
                            uuid = target_slot.get('buy_order_uuid')
                            if uuid:
                                self.upbit.cancel_order(uuid)
                                self.log(f"Direct Command: Canceled buy order {uuid} for {market}")
                            self.remove_slot(target_slot, cooldown=False) 
                        else:
                            self.log(f"COMMAND FAILED: Slot not found or not in BUY_WAIT for {market}")
                
                os.remove(COMMAND_FILE)
            except Exception as e:
                self.log(f"Error processing command: {e}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    trader = AutoTrader()
    trader.run()
