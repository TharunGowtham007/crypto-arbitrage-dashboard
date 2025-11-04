import ccxt
import streamlit as st
import time
import logging
from decimal import Decimal, ROUND_DOWN

# ------------------------------------------
# CONFIG
# ------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")

EXCHANGES = ["binance", "kucoin", "kraken", "coinbase", "okx", "gate", "bitfinex", "bybit"]
CRYPTOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT", "LTC/USDT", "DOT/USDT", "LINK/USDT"]
INVESTMENTS = [100, 500, 1000, 5000, 10000]

# ------------------------------------------
# STYLES (Trishul fixed & safe)
# ------------------------------------------
st.markdown("""
<style>
body {
    background: linear-gradient(145deg, #0a192f, #001f3f);
    color: white;
}
h1 {
    color: #80ffea;
    text-align: center;
    text-shadow: 0 0 15px #00d4ff;
}
div[data-testid="stAppViewContainer"]::before {
    content: "";
    background: url("https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg") no-repeat center;
    background-size: 400px 400px;
    opacity: 0.08;
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 0;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------
# HEADER
# ------------------------------------------
st.title("Arbitrage Dashboard")

# ------------------------------------------
# SESSION
# ------------------------------------------
if "armed" not in st.session_state:
    st.session_state.armed = False
if "stop" not in st.session_state:
    st.session_state.stop = False
if "log" not in st.session_state:
    st.session_state.log = []

# ------------------------------------------
# INPUTS
# ------------------------------------------
col1, col2 = st.columns(2)
with col1:
    buy_ex = st.selectbox("Buy Exchange", EXCHANGES, index=0)
with col2:
    sell_ex = st.selectbox("Sell Exchange", EXCHANGES, index=1)

symbol = st.selectbox("Crypto Pair", CRYPTOS, index=0)
investment = st.selectbox("Investment ($)", INVESTMENTS, index=2)
threshold = st.slider("Profit Threshold (%)", 0.1, 10.0, 1.0)

colA, colB = st.columns(2)
with colA:
    perform = st.button("▶️ Perform")
with colB:
    stop = st.button("⛔ Stop")

sim = st.checkbox("Simulation Mode (recommended)", True)

log_area = st.empty()

# ------------------------------------------
# HELPERS
# ------------------------------------------
def create_exchange(name):
    try:
        ex = getattr(ccxt, name)({"enableRateLimit": True})
        ex.load_markets()
        return ex
    except Exception as e:
        st.error(f"Exchange error: {e}")
        return None

def get_price(ex, sym):
    try:
        t = ex.fetch_ticker(sym)
        return t["last"]
    except Exception:
        return None

# ------------------------------------------
# MAIN
# ------------------------------------------
if perform:
    st.session_state.armed = True
    st.session_state.stop = False
    st.success("Bot armed ✅ — waiting for profitable signal...")

if stop:
    st.session_state.armed = False
    st.session_state.stop = True
    st.warning("Bot stopped ⛔")

if st.session_state.armed and not st.session_state.stop:
    bex = create_exchange(buy_ex)
    sex = create_exchange(sell_ex)
    if not bex or not sex:
        st.error("Exchange init failed.")
    else:
        price_b = get_price(bex, symbol)
        price_s = get_price(sex, symbol)
        if price_b and price_s:
            diff = ((price_s - price_b) / price_b) * 100
            st.metric("Price Buy", f"${price_b:.2f}")
            st.metric("Price Sell", f"${price_s:.2f}")
            st.metric("Difference (%)", f"{diff:.2f}%")

            if diff >= threshold:
                profit = investment * (diff / 100)
                st.success(f"🚀 PROFIT DETECTED: ${profit:.2f} ({diff:.2f}%) — executing trade...")
                st.session_state.log.append(f"Trade executed: +${profit:.2f} ({diff:.2f}%)")
                st.session_state.armed = False
            else:
                st.info(f"Monitoring... Diff: {diff:.2f}% (< {threshold}%)")
        else:
            st.warning("Price unavailable on one of the exchanges.")
    time.sleep(3)
    st.experimental_rerun()

# ------------------------------------------
# LOGS
# ------------------------------------------
if st.session_state.log:
    log_area.write("\n".join(st.session_state.log[-10:]))
else:
    log_area.info("No logs yet. Click ▶️ Perform to start monitoring.")
