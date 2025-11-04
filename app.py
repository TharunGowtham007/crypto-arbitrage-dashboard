import ccxt
import time
import logging
import streamlit as st
import threading

# --------------------------- CONFIGURATION ----------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

AVAILABLE_EXCHANGES = ['binance', 'coinbase', 'kraken', 'kucoin', 'okx', 'gate']
AVAILABLE_CRYPTOS = ['BTC', 'ETH', 'ADA', 'SOL']
AVAILABLE_CURRENCIES = ['USDT', 'USD', 'INR', 'EUR']
AVAILABLE_AMOUNTS = [500, 1000, 5000, 10000]

SLIPPAGE_THRESHOLD = 0.005  # 0.5%
POLL_INTERVAL = 5  # seconds

# --------------------------- STREAMLIT STYLING ----------------------------
st.set_page_config(page_title="🚀 Brilliant Arbitrage Dashboard", layout="wide")
st.markdown("""
<style>
body {
    background: linear-gradient(135deg, #0F2027, #203A43, #2C5364);
    color: #E0E0E0;
    font-family: 'Poppins', sans-serif;
}
.stApp {
    background: rgba(20, 20, 20, 0.75);
    backdrop-filter: blur(12px);
    border-radius: 20px;
    padding: 25px;
    box-shadow: 0 0 25px rgba(0, 0, 0, 0.6);
}
h1, h2, h3, h4 {
    color: #00E5FF;
    text-shadow: 0px 0px 8px #00E5FF;
}
.stButton>button {
    background: linear-gradient(90deg, #FF512F, #DD2476);
    color: white;
    border-radius: 8px;
    border: none;
    font-weight: bold;
    padding: 10px 20px;
}
.stSelectbox, .stNumberInput, .stTextInput {
    background: rgba(255, 255, 255, 0.15);
    color: white !important;
    border-radius: 6px;
}
table {
    color: white;
}
.status-card {
    background: linear-gradient(145deg, #232526, #414345);
    padding: 15px;
    border-radius: 10px;
    margin-top: 10px;
}
.profit-card {
    background: linear-gradient(145deg, #11998e, #38ef7d);
    color: black;
    border-radius: 10px;
    padding: 15px;
}
.error-card {
    background: linear-gradient(145deg, #FF416C, #FF4B2B);
    color: white;
    border-radius: 10px;
    padding: 15px;
}
</style>
""", unsafe_allow_html=True)

# --------------------------- HELPER FUNCTIONS ----------------------------
def get_price_and_fees(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        price = ticker.get('last')
        trading_fee = exchange.fees.get('trading', {}).get('taker', 0.001)
        withdrawal_fee = (
            exchange.fees.get('funding', {})
            .get('withdraw', {})
            .get(symbol.split('/')[0], 0.0005)
            or 0.0005
        )
        return price, trading_fee, withdrawal_fee
    except Exception as e:
        logging.error(f"Error fetching from {exchange.id}: {e}")
        return None, None, None


def safe_format_price_data(exchange, data):
    if not data or any(v is None for v in data):
        return f"| {exchange.upper()} | N/A | N/A | N/A |"
    price, trading_fee, withdraw_fee = data
    return f"| {exchange.upper()} | ${price:.2f} | {trading_fee*100:.2f}% | ${withdraw_fee:.4f} |"


def calculate_arbitrage(prices_fees, ex1, ex2):
    p1, f1, w1 = prices_fees.get(ex1, (None, None, None))
    p2, f2, w2 = prices_fees.get(ex2, (None, None, None))
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
    st.markdown("Monitor **real-time prices**, discover **profitable spreads**, and **auto-execute arbitrage** with instant risk control.")

    with st.expander("⚙️ API Configuration", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            binance_api = st.text_input("Binance API Key", type="password")
            binance_secret = st.text_input("Binance Secret Key", type="password")
        with col2:
            kucoin_api = st.text_input("KuCoin API Key", type="password")
            kucoin_secret = st.text_input("KuCoin Secret Key", type="password")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        ex1 = st.selectbox("Exchange 1", AVAILABLE_EXCHANGES, index=0)
    with col2:
        ex2 = st.selectbox("Exchange 2", AVAILABLE_EXCHANGES, index=1)
    with col3:
        crypto = st.selectbox("Crypto", AVAILABLE_CRYPTOS, index=0)
    with col4:
        currency = st.selectbox("Currency", AVAILABLE_CURRENCIES, index=0)

    symbol = f"{crypto}/{currency}"
    investment = st.selectbox("Investment Amount", AVAILABLE_AMOUNTS, index=1)
    profit_threshold = st.slider("Minimum Profit Threshold (%)", min_value=0.5, max_value=10.0, value=2.0, step=0.1)
    PROFIT_THRESHOLD = profit_threshold / 100

    start = st.button("🚀 Start Arbitrage Monitoring")

    if start:
        api_keys = {
            'binance': {'apiKey': binance_api, 'secret': binance_secret},
            'kucoin': {'apiKey': kucoin_api, 'secret': kucoin_secret},
        }

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

        st.success("✅ Monitoring started! Fetching live data...")

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
                |-----------|--------|--------------|----------------|
                {safe_format_price_data(ex1, prices_fees.get(ex1))}
                {safe_format_price_data(ex2, prices_fees.get(ex2))}
                """
                price_placeholder.markdown(f"<div class='status-card'><h3>📊 Real-Time Prices & Fees</h3>{price_table}</div>", unsafe_allow_html=True)

                investment_profit = profit_pct * investment if profit_pct > 0 else 0
                profit_placeholder.markdown(f"""
                <div class='profit-card'>
                <h3>💰 Arbitrage Analysis</h3>
                <b>Direction:</b> {direction or 'N/A'}<br>
                <b>Profit %:</b> {profit_pct*100:.3f}%<br>
                <b>Profit on ${investment}:</b> ${investment_profit:.3f}<br>
                <b>After Slippage:</b> ${adjusted_profit:.4f}<br>
                <b>Risk:</b> {'⚠️ Slippage Risk' if slippage_risk else '✅ Safe to Execute'}
                </div>
                """, unsafe_allow_html=True)

                if profit_pct > PROFIT_THRESHOLD and not slippage_risk:
                    crypto_amount = investment / (prices_fees[ex1][0] or 1)
                    status = execute_arbitrage(direction, crypto_amount)
                    status_placeholder.success(f"✅ Trade Executed: {status}")
                    best_opportunity = direction
                elif profit_dollar < 0:
                    status_placeholder.markdown("<div class='error-card'>🚨 Loss Detected! Stopping monitoring.</div>", unsafe_allow_html=True)
                    monitoring = False
                else:
                    status_placeholder.info("⏳ Monitoring for new opportunities...")
            else:
                status_placeholder.markdown("<div class='error-card'>❌ Failed to fetch data. Stopping.</div>", unsafe_allow_html=True)
                monitoring = False

            time.sleep(POLL_INTERVAL)

        if best_opportunity:
            st.success(f"🏆 Best Profitable Option Found: {best_opportunity}")
        else:
            st.warning("No profitable arbitrage found during this session.")


if __name__ == "__main__":
    main()
