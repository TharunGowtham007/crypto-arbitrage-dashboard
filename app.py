import ccxt
import streamlit as st
import time
import logging
import datetime
from decimal import Decimal

# ------------------------------------------
# BASIC CONFIG
# ------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")

EXCHANGES = ccxt.exchanges  # Full list of CCXT-supported exchanges

# ------------------------------------------
# [Your existing STYLE and HEADER sections remain unchanged]
# ------------------------------------------

# ------------------------------------------
# SESSION
# ------------------------------------------
if "armed" not in st.session_state:
    st.session_state.armed = False
if "stop" not in st.session_state:
    st.session_state.stop = False
if "log" not in st.session_state:
    st.session_state.log = []
if "common_symbols" not in st.session_state:
    st.session_state.common_symbols = []  # Cache for common pairs
if "markets_loaded" not in st.session_state:
    st.session_state.markets_loaded = False

# ------------------------------------------
# INPUT UI
# ------------------------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Configuration")

col1, col2 = st.columns(2)
with col1:
    buy_ex = st.selectbox("Buy Exchange", EXCHANGES, index=0)
    buy_api_key = st.text_input(f"{buy_ex.capitalize()} API Key", type="password", key="buy_key")
    buy_secret = st.text_input(f"{buy_ex.capitalize()} Secret", type="password", key="buy_secret")
with col2:
    sell_ex = st.selectbox("Sell Exchange", EXCHANGES, index=1)
    sell_api_key = st.text_input(f"{sell_ex.capitalize()} API Key", type="password", key="sell_key")
    sell_secret = st.text_input(f"{sell_ex.capitalize()} Secret", type="password", key="sell_secret")

# Load markets button (to fetch available pairs)
load_markets = st.button("🔄 Load Available Pairs")
if load_markets:
    # Create exchanges (without full init yet, just for markets)
    buy_temp = create_exchange(buy_ex, buy_api_key, buy_secret)
    sell_temp = create_exchange(sell_ex, sell_api_key, sell_secret)
    
    if not buy_temp or not sell_temp:
        st.error("Failed to initialize one or both exchanges. Check API keys or try a different exchange.")
        st.session_state.common_symbols = []
        st.session_state.markets_loaded = False
    else:
        try:
            # Fetch markets (this loads symbols)
            buy_markets = set(buy_temp.symbols)  # All symbols on buy exchange
            sell_markets = set(sell_temp.symbols)  # All symbols on sell exchange
            common = sorted(list(buy_markets & sell_markets))  # Intersection, sorted
            st.session_state.common_symbols = common
            st.session_state.markets_loaded = True
            st.success(f"Loaded {len(common)} common pairs from {buy_ex} and {sell_ex}.")
        except Exception as e:
            st.error(f"Error loading markets: {e}")
            st.session_state.common_symbols = []
            st.session_state.markets_loaded = False

# Dynamic pair selection
if st.session_state.markets_loaded and st.session_state.common_symbols:
    symbol = st.selectbox("Crypto Pair", st.session_state.common_symbols, index=0 if st.session_state.common_symbols else None)
else:
    st.warning("Click '🔄 Load Available Pairs' to populate the list. (No pairs loaded yet.)")
    symbol = st.text_input("Crypto Pair (e.g., BTC/USDT, ETH/BTC)", value="BTC/USDT")  # Fallback to text input

investment = st.number_input("Investment ($)", min_value=1.0, value=1000.0, step=1.0)
threshold = st.slider("Profit Threshold (%)", 0.1, 10.0, 1.0)

colA, colB = st.columns(2)
with colA:
    perform = st.button("▶️ Perform")
with colB:
    stop = st.button("⛔ Stop")

sim = st.checkbox("Simulation Mode", True)
st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------
# [Your existing EXCHANGE HELPERS, MAIN LOGIC, and TRADE HISTORY sections remain unchanged]
# ------------------------------------------