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

EXCHANGES = ccxt.exchanges

# ------------------------------------------
# STYLE (Dark + Faint Golden Trishul)
# ------------------------------------------
st.markdown("""
<style>
body, div[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at center, #1a1a1a 0%, #000000 100%);
    color: #f8f9fa;
    font-family: "Segoe UI", sans-serif;
    overflow: hidden;
}

/* Full-screen faint gold Trishul background */
body::before {
    content: "🔱";
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 600px;
    color: rgba(212,175,55,0.08);
    z-index: 0;
    pointer-events: none;
    user-select: none;
}

/* Main container styling */
div[data-testid="stAppViewContainer"] > .main {
    position: relative;
    z-index: 1;
}

/* Headers and blocks */
h1, h2, h3, h4, h5, h6 {
    color: #f8f9fa;
    text-align: center;
}

.block {
    background: rgba(255,255,255,0.05);
    border-radius: 10px;
    padding: 20px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.3);
    margin-bottom: 20px;
    z-index: 2;
}

/* Metric boxes */
.metric-green { background-color: rgba(40,167,69,0.15); border-left: 4px solid #28a745; padding: 15px; border-radius: 8px; }
.metric-red { background-color: rgba(220,53,69,0.15); border-left: 4px solid #dc3545; padding: 15px; border-radius: 8px; }
.metric-profit { background-color: rgba(255,193,7,0.15); border-left: 4px solid #ffc107; padding: 15px; border-radius: 8px; }

/* Buttons */
.stButton>button {
    background-color: #d4af37;
    color: #000;
    border: none;
    border-radius: 5px;
    padding: 10px 20px;
    font-size: 16px;
    font-weight: bold;
}
.stButton>button:hover {
    background-color: #b08b2b;
}

/* Inputs */
.stSelectbox, .stSlider, .stTextInput, .stNumberInput {
    margin-bottom: 15px;
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

symbol = st.text_input("Crypto Pair (e.g., BTC/USDT, ETH/BTC)", value="BTC/USDT")
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
# EXCHANGE HELPERS
# ------------------------------------------
def create_exchange(name, api_key=None, secret=None):
    try:
        config = {"enableRateLimit": True}
        if api_key and secret:
            config.update({"apiKey": api_key, "secret": secret})
        ex = getattr(ccxt, name)(config)
        ex.load_markets()
        return ex
    except Exception as e:
        st.warning(f"{name.capitalize()} unavailable: {e}")
        return None

def get_price(ex, sym):
    try:
        t = ex.fetch_ticker(sym)
        return t["last"]
    except Exception as e:
        logging.error(f"Failed to fetch price: {e}")
        return None

def get_fee(ex, sym, side, amount, price):
    """Fetch estimated real-time trading fee using CCXT market fee structure"""
    try:
        market = ex.market(sym)
        if side == "buy":
            fee = market.get("maker", 0.001)
        else:
            fee = market.get("taker", 0.001)
        return Decimal(fee)
    except Exception as e:
        logging.warning(f"Fee fetch failed for {ex.id}: {e}")
        return Decimal("0.001")

# ------------------------------------------
# MAIN LOGIC
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
    buy = create_exchange(buy_ex, buy_api_key, buy_secret)
    sell = create_exchange(sell_ex, sell_api_key, sell_secret)

    if not buy or not sell:
        st.error("Exchange initialization failed.")
    else:
        if symbol not in buy.markets or symbol not in sell.markets:
            st.error(f"Pair '{symbol}' not available on both exchanges.")
            st.session_state.armed = False
        else:
            pb = get_price(buy, symbol)
            ps = get_price(sell, symbol)
            if pb and ps:
                buy_fee = get_fee(buy, symbol, "buy", 1, pb)
                sell_fee = get_fee(sell, symbol, "sell", 1, ps)

                # Calculate profit with real fees
                diff = ((ps - pb) / pb) * 100
                fee_cost = (buy_fee + sell_fee) * 100
                net_diff = diff - fee_cost
                profit = investment * (net_diff / 100)

                colx, coly, colz = st.columns(3)
                with colx:
                    st.markdown(f"<div class='metric-green'><h4>Buy @ {buy_ex.capitalize()}</h4><p>${pb:.2f}</p></div>", unsafe_allow_html=True)
                with coly:
                    st.markdown(f"<div class='metric-red'><h4>Sell @ {sell_ex.capitalize()}</h4><p>${ps:.2f}</p></div>", unsafe_allow_html=True)
                with colz:
                    st.markdown(f"<div class='metric-profit'><h4>Profit (after fees)</h4><p>${profit:.2f} ({net_diff:.2f}%)</p></div>", unsafe_allow_html=True)

                if net_diff <= 0:
                    st.warning("⚠️ Loss detected — stopping trade immediately.")
                    st.session_state.armed = False
                elif net_diff >= threshold:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if sim:
                        st.success(f"🚀 PROFIT DETECTED (SIM): +${profit:.2f} ({net_diff:.2f}%)")
                        st.session_state.log.append(f"{timestamp}: Simulated profit +${profit:.2f}")
                    else:
                        st.success(f"🚀 REAL PROFIT DETECTED: +${profit:.2f} ({net_diff:.2f}%)")
                        st.session_state.log.append(f"{timestamp}: Real profit +${profit:.2f}")
                    st.session_state.armed = False
                else:
                    st.info(f"Monitoring... Diff: {net_diff:.2f}% (< {threshold}%)")
            else:
                st.warning("Price unavailable.")

    # safe rerun (no crashes)
    if not st.session_state.stop:
        time.sleep(5)
        st.session_state.refresh_flag = not st.session_state.get("refresh_flag", False)
        st.rerun()

# ------------------------------------------
# TRADE HISTORY
# ------------------------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Recent Trades History")
if st.session_state.log:
    st.write("\n".join(st.session_state.log[-20:]))
else:
    st.info("No trades yet. Click ▶️ Perform to start monitoring.")
st.markdown('</div>', unsafe_allow_html=True)
