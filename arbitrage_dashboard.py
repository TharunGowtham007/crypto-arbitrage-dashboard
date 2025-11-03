import ccxt
import time
import logging
import streamlit as st
import requests
import threading
from decimal import Decimal, ROUND_DOWN

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Trading pair
SYMBOL = 'BTC/USDT'

# Arbitrage settings
PROFIT_THRESHOLD = 0.001  # 0.1% minimum profit
SLIPPAGE_THRESHOLD = 0.005  # 0.5% slippage check
POLL_INTERVAL = 5  # Seconds between checks
MIN_TRADE_AMOUNT = 0.001  # Minimum BTC

# List of supported exchanges (expanded for brilliance; add/remove as needed)
EXCHANGES = [
    'binance', 'coinbase', 'kraken', 'zebpay', 'bitfinex', 'huobi', 'okx', 'kucoin', 'gate', 'bybit'
    # For DeFi, add 'uniswap' but requires web3 setup (see notes)
]

# API Keys (set for real trading; None for simulation)
API_KEYS = {
    'binance': {'apiKey': None, 'secret': None},
    'coinbase': {'apiKey': None, 'secret': None},
    'kraken': {'apiKey': None, 'secret': None},
    'zebpay': {'apiKey': None, 'secret': None},
    'bitfinex': {'apiKey': None, 'secret': None},
    'huobi': {'apiKey': None, 'secret': None},
    'okx': {'apiKey': None, 'secret': None},
    'kucoin': {'apiKey': None, 'secret': None},
    'gate': {'apiKey': None, 'secret': None},
    'bybit': {'apiKey': None, 'secret': None},
}

# Initialize exchanges
exchange_instances = {}
for ex in EXCHANGES:
    try:
        exchange_instances[ex] = ccxt.__dict__[ex]({
            'apiKey': API_KEYS[ex]['apiKey'],
            'secret': API_KEYS[ex]['secret'],
            'enableRateLimit': True,
        })
    except Exception as e:
        logging.warning(f"Failed to initialize {ex}: {e}")

# Function to fetch price and fees
def get_price_and_fees(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        trading_fee = exchange.fees.get('trading', {}).get('taker', 0.001)  # Default 0.1%
        withdrawal_fee = exchange.fees.get('funding', {}).get('withdraw', {}).get(symbol.split('/')[0], 0.0005) or 0.0005
        return price, trading_fee, withdrawal_fee
    except Exception as e:
        logging.error(f"Error fetching from {exchange.id}: {e}")
        return None, None, None

# Function to calculate arbitrage across all exchanges (returns dollar profit and pct)
def calculate_arbitrage(prices_fees):
    best_profit_dollar = -float('inf')
    best_profit_pct = -float('inf')
    best_direction = None
    for ex1, (price1, fee1, withdraw1) in prices_fees.items():
        for ex2, (price2, fee2, withdraw2) in prices_fees.items():
            if ex1 == ex2 or not all([price1, price2, fee1, fee2, withdraw1, withdraw2]):
                continue
            # Buy on ex1, sell on ex2
            buy_cost = price1 * (1 + fee1) + withdraw1
            sell_revenue = price2 * (1 - fee2)
            profit_dollar = sell_revenue - buy_cost
            profit_pct = (profit_dollar / buy_cost) if buy_cost > 0 else 0
            if profit_pct > best_profit_pct:
                best_profit_dollar = profit_dollar
                best_profit_pct = profit_pct
                best_direction = f'Buy {ex1}, Sell {ex2}'
    return best_profit_dollar, best_profit_pct, best_direction

# Slippage check (now on dollar profit)
def check_slippage_risk(profit_dollar):
    if profit_dollar <= 0:
        return True, profit_dollar  # Already loss
    slippage_impact = profit_dollar * SLIPPAGE_THRESHOLD
    adjusted_profit = profit_dollar - slippage_impact
    return adjusted_profit < 0, adjusted_profit

# Execute arbitrage
def execute_arbitrage(direction, amount):
    if not any(API_KEYS[ex]['apiKey'] for ex in EXCHANGES):
        return "Simulation: Arbitrage executed"
    # Parse direction and execute (simplified; add real logic)
    logging.info(f"Executing {direction} for {amount} {SYMBOL.split('/')[0]}")
    return f"Executed: {direction}"

# Streamlit Dashboard
def run_dashboard():
    st.title("Multi-Exchange Crypto Arbitrage Dashboard")
    st.markdown(f"**Symbol:** {SYMBOL} | **Profit Threshold:** {PROFIT_THRESHOLD * 100}% | **Slippage Threshold:** {SLIPPAGE_THRESHOLD * 100}%")
    
    price_placeholder = st.empty()
    profit_placeholder = st.empty()
    status_placeholder = st.empty()
    
    while True:
        prices_fees = {}
        threads = []
        def fetch(ex):
            prices_fees[ex] = get_price_and_fees(exchange_instances[ex], SYMBOL)
        
        for ex in exchange_instances:
            t = threading.Thread(target=fetch, args=(ex,))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        
        if prices_fees:
            profit_dollar, profit_pct, direction = calculate_arbitrage(prices_fees)
            slippage_risk, adjusted_profit = check_slippage_risk(profit_dollar)
            
            # Clean display: Filter valid data and format as list
            valid_prices = [(ex, p, f, w) for ex, (p, f, w) in prices_fees.items() if p is not None]
            price_data = "\n".join([f"- {ex}: ${p:.2f} (Trading Fee: {f*100:.2f}%, Withdrawal Fee: {w})" for ex, p, f, w in valid_prices])
            price_placeholder.markdown(f"**Real-Time Prices & Fees:**\n{price_data}")
            
            profit_placeholder.markdown(f"**Best Arbitrage:** {direction or 'None'} | Profit: ${profit_dollar:.4f} ({profit_pct*100:.2f}%) | Adjusted: ${adjusted_profit:.4f} | Slippage Risk: {'Yes' if slippage_risk else 'No'}")
            
            if profit_pct > PROFIT_THRESHOLD and not slippage_risk:
                status = execute_arbitrage(direction, MIN_TRADE_AMOUNT)
                status_placeholder.success(f"Arbitrage Triggered: {status}")
            else:
                status_placeholder.info("No profitable opportunity.")
        else:
            price_placeholder.markdown("**Prices:** Unable to fetch from any exchange.")
            profit_placeholder.markdown("**Arbitrage:** N/A")
            status_placeholder.error("API Errors on all exchanges.")
        
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_dashboard()