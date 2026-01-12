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
LOG_DIR = "logs"

class AutoTrader:
    def __init__(self):
        self.setup_logging()
        self.access_key = os.getenv("UPBIT_ACCESS_KEY")
        self.secret_key = os.getenv("UPBIT_SECRET_KEY")
        self.trade_amount = float(os.getenv("TRADE_AMOUNT", 10000))
        self.max_slots = int(os.getenv("MAX_SLOTS", 3))
        self.upbit = pyupbit.Upbit(self.access_key, self.secret_key)
        self.state = self.load_state()
        self.last_summary_date = datetime.date.today()

    def load_state(self):
        state = {"slots": []}
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
        self.state = {"status": "WAITING"}
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

    def run(self):
        self.log(f"AutoTrader started with amount: {self.trade_amount} KRW, Max Slots: {self.max_slots}")
        while True:
            try:
                # Check daily summary
                self.check_daily_summary()
                
                # Check Market Condition (Circuit Breaker)
                is_market_good = self.check_market_condition()
                
                # 1. Process existing slots
                # We iterate a copy to verify/modify safely if needed, though direct access is fine if we don't delete mid-loop
                # If we remove a slot, we should do it carefully. 
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
                
                # 2. Search for new target if slots available and market is good
                if is_market_good and len(self.state['slots']) < self.max_slots:
                    self.try_search_and_enter()
                    
                time.sleep(1)
            except Exception as e:
                self.log(f"Error in main loop: {e}")
                time.sleep(5)

    def try_search_and_enter(self):
        # Throttle search to avoid spamming API if no target found
        now = time.time()
        last_search = self.state.get('last_search_time', 0)
        if now - last_search < 10: 
            return

        self.state['last_search_time'] = now
        # We don't verify save_state here to avoid IO, just in memory is fine for throttling
        
        self.log("Searching for new target...")
        
        # Exclude currently held markets
        held_markets = [s['market'] for s in self.state['slots'] if 'market' in s]
        
        candidates = trend.get_candidates()
        strict_coins = trend.scan_trends(candidates, strict_slope=True)
        
        # Filter out held markets
        target_coins = [c for c in strict_coins if c['market'] not in held_markets]
        
        if not target_coins:
            self.log("No new target found.")
            return

        # Sort by disparity
        target_coins.sort(key=lambda x: x['disparity_5_20'])
        target = target_coins[0]
        market = target['market']

        self.log(f"Target found: {target['korean_name']} ({market})")
        
        current_price = pyupbit.get_current_price(market)
        tick = self.get_tick_size(current_price)
        buy_price = current_price - tick # 1 tick lower
        
        # Place limit order
        ret = self.upbit.buy_limit_order(market, buy_price, self.trade_amount / buy_price)
        if ret and 'uuid' in ret:
            new_slot = {
                "status": "BUY_ORDER_WAITING",
                "market": market,
                "buy_order_uuid": ret['uuid'],
                "order_price": buy_price,
                "order_time": datetime.datetime.now().isoformat()
            }
            self.state['slots'].append(new_slot)
            self.save_state()
            self.log(f"Buy order placed for {market}. Slot occupied.")
        else:
            self.log(f"Failed to place order for {market}: {ret}")

    def process_slot(self, slot, index):
        status = slot.get("status")
        if status == "BUY_ORDER_WAITING":
            self.step_buy_order_waiting(slot)
        elif status == "HOLDING":
            self.step_holding(slot)

    def remove_slot(self, slot):
        # Mark for removal
        slot['status'] = 'DONE'
        # Actual removal happens in main loop

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
            
        print(f"Slot {market}: Waiting for buy order to fill... ({int(elapsed)}s elapsed)", end='\r')
        
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
                self.log(f"Order for {market} canceled externally.")
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
        
        print(f"Slot {market}: {curr_price}, Avg: {avg_price:.0f}, Ret: {profit_rate*100:.2f}%", end='\r')
        
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

        # 1-2. Stop Loss (-2%)
        if profit_rate <= -0.02:
            self.log(f"DEFENSE: Stop loss triggered for {market} ({profit_rate*100:.2f}%). Selling...")
            self.sell_market(slot, "Stop Loss", profit_rate)
            return

        # 2. Add-buy Strategy (30 mins passed, loss, not yet added)
        entry_time = datetime.datetime.fromisoformat(slot['entry_time'])
        elapsed_mins = (datetime.datetime.now() - entry_time).total_seconds() / 60
        
        if elapsed_mins >= 30 and profit_rate < 0 and not slot.get('add_buy_done', False):
            self.log(f"EXIT STRATEGY: 30 mins w/ loss for {market}. Executing Add-buy...")
            ret = self.upbit.buy_market_order(market, self.trade_amount)
            if ret and 'uuid' in ret:
                # Wait a bit for order to fill and balances to update
                time.sleep(2)
                # Recalculate average price (fetch from upbit balance)
                self.update_avg_price(slot)
                slot['add_buy_done'] = True
                # Reset highest price to current to restart trailing logic
                slot['highest_price'] = curr_price 
                self.save_state()
                self.log(f"Add-buy complete for {market}. Avg price updated.")
            return

        # 3. Take Profit (Trailing Stop)
        # Active only if max profit reached +0.5%
        max_profit_rate = (highest_price - avg_price) / avg_price
        
        if max_profit_rate >= 0.005:
            # Drop from highest
            drop_rate = (highest_price - curr_price) / highest_price
            if drop_rate >= 0.002: # 0.2% drop
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
