import ccxt
import streamlit as st
import time
import logging
from decimal import Decimal

# ------------------------------------------
# BASIC CONFIG
# ------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")

EXCHANGES = ["binance", "binanceus", "kucoin", "kraken", "coinbase", "okx", "bitfinex", "bybit"]
CRYPTOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT"]
INVESTMENTS = [100, 500, 1000, 5000, 10000]

# ------------------------------------------
# STYLE (Trishul + Enhanced Graphics)
# ------------------------------------------
st.markdown("""
<style>
body {
    background: radial-gradient(circle at top left, #001F3F, #000814);
    color: white;
    font-family: "Segoe UI", sans-serif;
}

div[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at center, #001F3F, #000814);
}

div[data-testid="stAppViewContainer"]::before {
    content: "";
    background: url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg') no-repeat center;
    background-size: 380px 380px;
    opacity: 0.06;
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 100%;
    height: 100%;
    z-index: 0;
}

h1 {
    color: #79e0ee;
    text-align: center;
    text-shadow: 0px 0px 20px #00eaff;
    font-weight: 700;
    animation: glow 2s ease-in-out infinite alternate;
}
@keyframes glow {
    from { text-shadow: 0 0 10px #00eaff; }
    to { text-shadow: 0 0 30px #00eaff, 0 0 40px #00ffff; }
}

.block {
    background: rgba(255,255,255,0.08);
    border-radius: 20px;
    padding: 20px;
    box-shadow: 0 0 10px rgba(0,255,255,0.1);
    z-index: 1;
}
.metric-green {
    background-color: rgba(0,255,0,0.2);
    padding: 10px;
    border-radius: 10px;
}
.metric-red {
    background-color: rgba(255,0,0,0.2);
    padding: 10px;
    border-radius: 10px;
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
# INPUT UI
# ------------------------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
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
sim = st.checkbox("Simulation Mode", True)
st.markdown('</div>', unsafe_allow_html=True)

log_area = st.empty()

# ------------------------------------------
# EXCHANGE HELPERS
# ------------------------------------------
def create_exchange(name):
    try:
        ex = getattr(ccxt, name)({"enableRateLimit": True})
        ex.load_markets()
        return ex
    except Exception as e:
        st.warning(f"{name.capitalize()} unavailable, switching automatically if possible.")
        return None

def get_price(ex, sym):
    try:
        t = ex.fetch_ticker(sym)
        return t["last"]
    except Exception:
        return None

# ------------------------------------------
# MAIN LOOP
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
    buy = create_exchange(buy_ex)
    sell = create_exchange(sell_ex)

    if not buy or not sell:
        st.error("Exchange initialization failed. Try switching to different exchanges.")
    else:
        pb = get_price(buy, symbol)
        ps = get_price(sell, symbol)
        if pb and ps:
            diff = ((ps - pb) / pb) * 100
            colx, coly, colz = st.columns(3)
            with colx:
                st.markdown(f"<div class='metric-green'><h3>Buy @ {buy_ex.capitalize()}</h3><p>${pb:.2f}</p></div>", unsafe_allow_html=True)
            with coly:
                st.markdown(f"<div class='metric-red'><h3>Sell @ {sell_ex.capitalize()}</h3><p>${ps:.2f}</p></div>", unsafe_allow_html=True)
            with colz:
                st.metric("Difference", f"{diff:.2f}%")

            if diff >= threshold:
                profit = investment * (diff / 100)
                st.success(f"🚀 PROFIT DETECTED: +${profit:.2f} ({diff:.2f}%) — executing trade...")
                st.session_state.log.append(f"Trade executed: +${profit:.2f} ({diff:.2f}%)")
                st.session_state.armed = False
            else:
                st.info(f"Monitoring... Diff: {diff:.2f}% (< {threshold}%)")
        else:
            st.warning("Price unavailable on one or both exchanges.")
    time.sleep(3)
    st.rerun()

# ------------------------------------------
# LOGS
# ------------------------------------------
if st.session_state.log:
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.write("\n".join(st.session_state.log[-10:]))
    st.markdown('</div>', unsafe_allow_html=True)
else:
    log_area.info("No logs yet. Click ▶️ Perform to start monitoring.")
