import ccxt
import streamlit as st
import time
import logging
import pandas as pd
from decimal import Decimal

# ------------------------------------------
# BASIC CONFIG
# ------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide", page_icon="🔱")

# ------------------------------------------
# CUSTOM STYLE — GOLDEN TRISHUL BACKGROUND
# ------------------------------------------
st.markdown("""
<style>
body {
    background-color: #0d0d0d;
    color: #e6e6e6;
    font-family: 'Segoe UI', sans-serif;
}

.trishul-bg {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 300px;
    color: rgba(212, 175, 55, 0.07); /* faint golden */
    z-index: -1;
    user-select: none;
}

@media (max-width: 768px) {
    .trishul-bg {
        font-size: 150px;
    }
}

.block-container {
    background: rgba(20, 20, 20, 0.95);
    border-radius: 15px;
    padding: 1.5rem;
    box-shadow: 0 0 20px rgba(212, 175, 55, 0.15);
}
</style>

<div class="trishul-bg">🔱</div>
""", unsafe_allow_html=True)

# ------------------------------------------
# TITLE
# ------------------------------------------
st.markdown("<h1 style='text-align:center; color:#d4af37;'>Arbitrage Dashboard</h1>", unsafe_allow_html=True)

# ------------------------------------------
# EXCHANGE SELECTION
# ------------------------------------------
exchanges_list = ["binance", "kucoin", "bitget", "bybit", "kraken"]
exchange1_name = st.selectbox("Select Exchange 1", exchanges_list)
exchange2_name = st.selectbox("Select Exchange 2", exchanges_list)

api_key_1 = st.text_input(f"{exchange1_name} API Key", type="password")
secret_key_1 = st.text_input(f"{exchange1_name} Secret Key", type="password")

api_key_2 = st.text_input(f"{exchange2_name} API Key", type="password")
secret_key_2 = st.text_input(f"{exchange2_name} Secret Key", type="password")

crypto_symbol = st.text_input("Enter Crypto Symbol (e.g., BTC/USDT)", value="BTC/USDT")

# ------------------------------------------
# FUNCTION: Create Exchange Instance
# ------------------------------------------
def create_exchange(name, api_key, secret):
    try:
        exchange_class = getattr(ccxt, name)
        exchange = exchange_class({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True
        })
        exchange.load_markets()
        return exchange
    except Exception as e:
        st.error(f"Exchange init failed for {name}: {e}")
        return None

# ------------------------------------------
# FUNCTION: Fetch Prices & Fees
# ------------------------------------------
def fetch_prices_and_fees(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        fees = exchange.fetch_trading_fee(symbol)
        maker_fee = fees.get("maker", 0)
        taker_fee = fees.get("taker", 0)
        return price, maker_fee, taker_fee
    except Exception:
        return None, None, None

# ------------------------------------------
# MAIN PROCESS
# ------------------------------------------
if st.button("Start Arbitrage Bot 🚀"):
    with st.spinner("Bot armed ✅ — waiting for profitable signal..."):
        ex1 = create_exchange(exchange1_name, api_key_1, secret_key_1)
        ex2 = create_exchange(exchange2_name, api_key_2, secret_key_2)

        if not ex1 or not ex2:
            st.warning("Exchange initialization failed. Try switching to different exchanges.")
        else:
            while True:
                price1, maker1, taker1 = fetch_prices_and_fees(ex1, crypto_symbol)
                price2, maker2, taker2 = fetch_prices_and_fees(ex2, crypto_symbol)

                if not price1 or not price2:
                    st.error("Failed to fetch prices. Retrying...")
                    time.sleep(3)
                    continue

                # Calculate effective prices including fees
                buy_price_effective = Decimal(price1) * (1 + Decimal(taker1))
                sell_price_effective = Decimal(price2) * (1 - Decimal(maker2))

                profit = sell_price_effective - buy_price_effective
                profit_percent = (profit / buy_price_effective) * 100

                if profit_percent > 0:
                    st.success(f"💰 Profit Opportunity Detected!")
                    st.write(f"Buy at **{exchange1_name.upper()}**: {price1}")
                    st.write(f"Sell at **{exchange2_name.upper()}**: {price2}")
                    st.write(f"Net Profit (after fees): **{profit:.2f} USD ({profit_percent:.2f}%)**")
                else:
                    st.info("⚠️ No profitable trade — bot paused to prevent loss.")
                    break

                time.sleep(5)

# ------------------------------------------
# FOOTER
# ------------------------------------------
st.markdown("<br><hr><p style='text-align:center; color:#888;'>© 2025 Trishul Arbitrage System</p>", unsafe_allow_html=True)
