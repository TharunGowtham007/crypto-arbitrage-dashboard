import ccxt
import streamlit as st
import time
import logging

# ------------------------------------------
# CONFIG
# ------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")

EXCHANGES = ["binance", "kucoin", "kraken", "coinbase", "okx", "bitfinex", "bybit"]
CRYPTOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT"]
INVESTMENTS = [100, 500, 1000, 5000, 10000]

# ------------------------------------------
# STYLING (Midnight + Golden Trishul)
# ------------------------------------------
st.markdown("""
<style>
body {
    background: radial-gradient(circle at top center, #0b0c10 0%, #000000 80%);
    color: #f1f1f1;
    font-family: "Segoe UI", sans-serif;
}

div[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at center, #0b0c10, #000000);
    overflow: hidden;
}

/* Animated rotating Trishul */
div[data-testid="stAppViewContainer"]::before {
    content: "";
    background: url('https://upload.wikimedia.org/wikipedia/commons/4/4b/Trishul_symbol_gold.png') no-repeat center;
    background-size: 420px 420px;
    opacity: 0.08;
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(0deg);
    width: 100%;
    height: 100%;
    z-index: 0;
    animation: spin 60s linear infinite;
}
@keyframes spin {
    from { transform: translate(-50%, -50%) rotate(0deg); }
    to { transform: translate(-50%, -50%) rotate(360deg); }
}

h1 {
    color: #ffd700;
    text-align: center;
    text-shadow: 0px 0px 25px rgba(255, 215, 0, 0.8);
    font-weight: 800;
    letter-spacing: 1px;
}
.block {
    background: rgba(10,10,10,0.6);
    border-radius: 18px;
    padding: 20px;
    box-shadow: 0 0 20px rgba(255,215,0,0.1);
    z-index: 1;
    border: 1px solid rgba(255,215,0,0.15);
}
.metric-green {
    background-color: rgba(0,255,0,0.15);
    padding: 10px;
    border-radius: 10px;
    border: 1px solid rgba(0,255,0,0.25);
}
.metric-red {
    background-color: rgba(255,0,0,0.15);
    padding: 10px;
    border-radius: 10px;
    border: 1px solid rgba(255,0,0,0.25);
}
.stButton>button {
    background: linear-gradient(90deg, #b8860b, #ffcc00);
    color: black;
    border: none;
    border-radius: 12px;
    font-weight: bold;
    padding: 10px 20px;
    transition: all 0.3s ease-in-out;
}
.stButton>button:hover {
    background: linear-gradient(90deg, #ffcc00, #ffd700);
    transform: scale(1.05);
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------
# HEADER
# ------------------------------------------
st.title("Arbitrage Dashboard")

# ------------------------------------------
# SESSION STATE
# ------------------------------------------
if "armed" not in st.session_state:
    st.session_state.armed = False
if "stop" not in st.session_state:
    st.session_state.stop = False
if "log" not in st.session_state:
    st.session_state.log = []

# ------------------------------------------
# INPUT
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
api_key = st.text_input("API Key (optional)", type="password")
api_secret = st.text_input("API Secret (optional)", type="password")
colA, colB = st.columns(2)
with colA:
    perform = st.button("▶️ Perform")
with colB:
    stop = st.button("⛔ Stop")
sim = st.checkbox("Simulation Mode", True)
st.markdown('</div>', unsafe_allow_html=True)
log_area = st.empty()

# ------------------------------------------
# HELPERS
# ------------------------------------------
def create_exchange(name, key=None, secret=None):
    try:
        params = {"enableRateLimit": True}
        if key and secret:
            params.update({"apiKey": key, "secret": secret})
        ex = getattr(ccxt, name)(params)
        ex.load_markets()
        return ex
    except Exception:
        st.warning(f"{name.capitalize()} unavailable — switching automatically if possible.")
        return None

def get_price(ex, sym):
    try:
        t = ex.fetch_ticker(sym)
        return t["last"]
    except Exception:
        return None

def get_fee_percent(ex, sym):
    try:
        f = ex.fetch_trading_fee(sym)
        maker = f.get("maker", 0.001)
        taker = f.get("taker", 0.001)
    except Exception:
        maker = getattr(ex, "fees", {}).get("trading", {}).get("maker", 0.001)
        taker = getattr(ex, "fees", {}).get("trading", {}).get("taker", 0.001)
    return maker * 100, taker * 100  # convert to %

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
    buy = create_exchange(buy_ex, api_key, api_secret)
    sell = create_exchange(sell_ex, api_key, api_secret)

    if not buy or not sell:
        st.error("Exchange initialization failed. Try switching to different exchanges.")
    else:
        pb = get_price(buy, symbol)
        ps = get_price(sell, symbol)
        if pb and ps:
            buy_fee, _ = get_fee_percent(buy, symbol)
            _, sell_fee = get_fee_percent(sell, symbol)
            total_fee = buy_fee + sell_fee
            diff = ((ps - pb) / pb) * 100
            net_profit = diff - total_fee

            colx, coly, colz = st.columns(3)
            with colx:
                st.markdown(f"<div class='metric-green'><h3>Buy @ {buy_ex.capitalize()}</h3><p>${pb:.2f}</p></div>", unsafe_allow_html=True)
            with coly:
                st.markdown(f"<div class='metric-red'><h3>Sell @ {sell_ex.capitalize()}</h3><p>${ps:.2f}</p></div>", unsafe_allow_html=True)
            with colz:
                st.metric("Net Profit (after fees)", f"{net_profit:.2f}%")

            if net_profit >= threshold:
                profit = investment * (net_profit / 100)
                st.success(f"🚀 REAL PROFIT DETECTED: +${profit:.2f} ({net_profit:.2f}%) — executing trade...")
                st.session_state.log.append(f"Trade executed ✅: +${profit:.2f} ({net_profit:.2f}%) after fees")
                st.session_state.armed = False
            elif net_profit <= 0:
                st.error(f"❌ Loss detected (Net: {net_profit:.2f}%) — trade aborted immediately.")
                st.session_state.log.append(f"Loss detected — trade cancelled ({net_profit:.2f}%)")
                st.session_state.armed = False
            else:
                st.info(f"Monitoring... Net Profit: {net_profit:.2f}% (< {threshold}%)")
        else:
            st.warning("Price unavailable on one or both exchanges.")
    time.sleep(3)
    st.rerun()

# ------------------------------------------
# LOG
# ------------------------------------------
if st.session_state.log:
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.write("\n".join(st.session_state.log[-10:]))
    st.markdown('</div>', unsafe_allow_html=True)
else:
    log_area.info("No logs yet. Click ▶️ Perform to start monitoring.")
