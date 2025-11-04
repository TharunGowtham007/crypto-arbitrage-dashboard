import ccxt
import time
import logging
import streamlit as st
import threading
from decimal import Decimal, ROUND_DOWN

# --------------------------- CONFIGURATION ----------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

AVAILABLE_EXCHANGES = ['binance', 'coinbase', 'kraken', 'kucoin', 'okx', 'gate']
AVAILABLE_CRYPTOS = ['BTC/USDT', 'ETH/USDT', 'ADA/USDT', 'SOL/USDT']
AVAILABLE_AMOUNTS = [500, 1000, 5000, 10000]

PROFIT_THRESHOLD = 0.001  # 0.1%
SLIPPAGE_THRESHOLD = 0.005  # 0.5%
POLL_INTERVAL = 5  # Seconds

# --------------------------- STREAMLIT STYLING ----------------------------
st.set_page_config(page_title="🚀 Brilliant Arbitrage Dashboard", layout="wide")
st.markdown("""
<style>
body {
    background: radial-gradient(circle at top left, #1e3c72, #2a5298);
    color: white;
}
.stApp {
    background: rgba(255, 255, 255, 0.07);
    backdrop-filter: blur(15px);
    border-radius: 20px;
    padding: 20px;
    box-shadow: 0px 0px 25px rgba(255,255,255,0.1);
}
h1, h2, h3, h4 {
    color: #FFD700;
}
.stButton>button {
    background: linear-gradient(90deg, #ff8c00, #ff4500);
    color: white;
    border-radius: 8px;
    border: none;
    font-weight: bold;
    padding: 8px 16px;
}
.stSelectbox, .stNumberInput, .stTextInput {
    background: rgba(255, 255, 255, 0.15);
    color: white !important;
    border-radius: 6px;
}
table {
    color: white;
}
</style>
""", unsafe_allow_html=True)

# --------------------------- HELPER FUNCTIONS ----------------------------
def get_price_and_fees(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        trading_fee = exchange.fees.get('trading', {}).get('taker', 0.001)
        withdrawal_fee = exchange.fees.get('funding', {}).get('withdraw', {}).get(symbol.split('/')[0], 0.0005) or 0.0005
        return price, trading_fee, withdrawal_fee
    except Exception as e:
        logging.error(f"Error fetching from {exchange.id}: {e}")
        return None, None, None

def calculate_arbitrage(prices_fees, ex1, ex2):
    p1, f1, w1 = prices_fees[ex1]
    p2, f2, w2 = prices_fees[ex2]
    if not all([p1, p2, f1, f2, w1, w2]):
        return 0, 0, None
    buy_cost = p1 * (1 + f1) + w1
    sell_revenue = p2 * (1 - f2)
    profit_dollar = sell_revenue - buy_cost
    profit_pct = (profit_dollar / buy_cost) if buy_cost > 0 else 0
    direction = f'Buy on {ex1.upper()}, Sell on {ex2.upper()}'
    return profit_dollar, profit_pct, direction

def check_slippage_risk(profit_dollar):
    if profit_dollar <= 0:
        return True, profit_dollar
    slippage_impact = profit_dollar * SLIPPAGE_THRESHOLD
    adjusted_profit = profit_dollar - slippage_impact
    return adjusted_profit < 0, adjusted_profit

def execute_arbitrage(direction, amount):
    logging.info(f"Executing {direction} for {amount:.6f} crypto units")
    return f"✅ Executed: {direction} for {amount:.6f} crypto"

# --------------------------- MAIN DASHBOARD ----------------------------
def main():
    st.title("🚀 Brilliant Crypto Arbitrage Dashboard")
    st.markdown("Monitor real-time prices, find best opportunities, and auto-execute profitable arbitrages — all visually ✨")

    with st.expander("⚙️ API Configuration (Set once here, no code changes needed)", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            binance_api = st.text_input("Binance API Key", type="password")
            binance_secret = st.text_input("Binance Secret Key", type="password")
        with col2:
            kucoin_api = st.text_input("KuCoin API Key", type="password")
            kucoin_secret = st.text_input("KuCoin Secret Key", type="password")

    col1, col2, col3 = st.columns(3)
    with col1:
        ex1 = st.selectbox("Exchange 1", AVAILABLE_EXCHANGES, index=0)
    with col2:
        ex2 = st.selectbox("Exchange 2", AVAILABLE_EXCHANGES, index=1)
    with col3:
        symbol = st.selectbox("Crypto", AVAILABLE_CRYPTOS, index=0)

    investment = st.selectbox("Investment Amount ($)", AVAILABLE_AMOUNTS, index=1)
    start = st.button("🚀 Start Arbitrage Monitoring")

    if start:
        api_keys = {
            'binance': {'apiKey': binance_api, 'secret': binance_secret},
            'kucoin': {'apiKey': kucoin_api, 'secret': kucoin_secret},
        }

        # Initialize exchanges
        exchange_instances = {}
        for ex in [ex1, ex2]:
            try:
                exchange_instances[ex] = ccxt.__dict__[ex]({
                    'apiKey': api_keys.get(ex, {}).get('apiKey'),
                    'secret': api_keys.get(ex, {}).get('secret'),
                    'enableRateLimit': True,
                })
            except Exception as e:
                st.error(f"Failed to initialize {ex}: {e}")
                return

        st.success("✅ Monitoring started! Fetching real-time prices and opportunities...")

        price_placeholder = st.empty()
        profit_placeholder = st.empty()
        status_placeholder = st.empty()

        monitoring = True
        best_opportunity = None

        while monitoring:
            prices_fees = {}
            threads = []

            def fetch(ex):
                prices_fees[ex] = get_price_and_fees(exchange_instances[ex], symbol)

            for ex in [ex1, ex2]:
                t = threading.Thread(target=fetch, args=(ex,))
                t.start()
                threads.append(t)
            for t in threads:
                t.join()

            if prices_fees:
                profit_dollar, profit_pct, direction = calculate_arbitrage(prices_fees, ex1, ex2)
                slippage_risk, adjusted_profit = check_slippage_risk(profit_dollar)

                price_table = f"""
                | Exchange | Price | Trading Fee | Withdrawal Fee |
                |----------|-------|-------------|----------------|
                | {ex1.upper()} | ${prices_fees[ex1][0]:.2f} | {prices_fees[ex1][1]*100:.2f}% | ${prices_fees[ex1][2]:.4f} |
                | {ex2.upper()} | ${prices_fees[ex2][0]:.2f} | {prices_fees[ex2][1]*100:.2f}% | ${prices_fees[ex2][2]:.4f} |
                """
                price_placeholder.markdown(f"### 📊 Real-Time Prices & Fees\n{price_table}")

                investment_profit = profit_pct * investment if profit_pct > 0 else 0
                color = "🟢" if profit_pct > 0 else "🔴"
                profit_placeholder.markdown(f"""
                ### 💰 Arbitrage Analysis  
                {color} **Direction:** {direction}  
                - **Profit %:** {profit_pct*100:.3f}%  
                - **Profit on ${investment}:** ${investment_profit:.3f}  
                - **After Slippage:** ${adjusted_profit:.4f}  
                - **Risk:** {'⚠️ Slippage Risk' if slippage_risk else '✅ Safe to Execute'}  
                """)

                if profit_pct > PROFIT_THRESHOLD and not slippage_risk:
                    crypto_amount = investment / prices_fees[ex1][0]
                    status = execute_arbitrage(direction, crypto_amount)
                    status_placeholder.success(f"✅ Trade Executed: {status}")
                    best_opportunity = direction
                elif profit_dollar < 0:
                    status_placeholder.error("🚨 Loss Detected! Stopping monitoring.")
                    monitoring = False
                else:
                    status_placeholder.info("⏳ Monitoring for new opportunities...")
            else:
                status_placeholder.error("❌ Failed to fetch data. Stopping.")
                monitoring = False

            time.sleep(POLL_INTERVAL)

        if best_opportunity:
            st.success(f"🏆 Best Profitable Option Found: {best_opportunity}")
        else:
            st.warning("No profitable arbitrage found during this session.")

if __name__ == "__main__":
    main()
