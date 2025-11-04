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

# All available exchanges from CCXT
EXCHANGES = ccxt.exchanges

# ------------------------------------------
# STYLE (Faint Golden Trishul + Mature Look)
# ------------------------------------------
st.markdown("""
<style>
body {
    background: radial-gradient(circle at top, #2b2b2b, #1a1a1a);
    color: #f8f9fa;
    font-family: "Segoe UI", sans-serif;
    overflow-x: hidden;
}

/* Faint Golden Trishul Background */
div[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at center, #2b2b2b, #121212);
}
div[data-testid="stAppViewContainer"]::before {
    content: "";
    background: url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg') no-repeat center;
    background-size: 420px 420px;
    opacity: 0.08;
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 100%;
    height: 100%;
    z-index: 0;
    filter: drop-shadow(0px 0px 10px rgba(255,215,0,0.4));
}

/* Title Glow */
h1 {
    color: #FFD700;
    text-align: center;
    font-weight: 700;
    text-shadow: 0px 0px 15px rgba(255,215,0,0.6);
    animation: glow 3s ease-in-out infinite alternate;
}
@keyframes glow {
    from { text-shadow: 0 0 10px rgba(255,215,0,0.4); }
    to { text-shadow: 0 0 30px rgba(255,215,0,0.8), 0 0 40px rgba(255,215,0,0.6); }
}

/* UI Blocks */
.block {
    background: rgba(255,255,255,0.08);
    border-radius: 15px;
    padding: 20px;
    box-shadow: 0 0 25px rgba(255,215,0,0.1);
    margin-bottom: 25px;
    z-index: 1;
}

/* Metrics Styling */
.metric-green {
    background-color: rgba(40,167,69,0.15);
    padding: 15px;
    border-radius: 10px;
    border-left: 4px solid #28a745;
}

.metric-red {
    background-color: rgba(220,53,69,0.15);
    padding: 15px;
    border-radius: 10px;
    border-left: 4px solid #dc3545;
}

.metric-profit {
    background-color: rgba(255,215,0,0.1);
    padding: 15px;
    border-radius: 10px;
    border-left: 4px solid #FFD700;
    box-shadow: 0 0 15px rgba(255,215,0,0.2);
}

/* Buttons */
.stButton>button {
    background: linear-gradient(to right, #FFD700, #ffb300);
    color: #1a1a1a;
    border: none;
    border-radius: 8px;
    padding: 12px 22px;
    font-size: 16px;
    font-weight: 600;
    transition: 0.3s;
}
.stButton>button:hover {
    background: linear-gradient(to right, #ffcc33, #e6a700);
    transform: scale(1.04);
}

/* Input Fields */
.stSelectbox, .stTextInput, .stNumberInput {
    border-radius: 5px;
    background-color: rgba(255,255,255,0.05);
}

/* Subheaders */
h2, h3, h4 {
    color: #f8f9fa;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------
# HEADER
# ------------------------------------------
st.title("Trishul Arbitrage Dashboard ⚡")

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
st.subheader("⚙️ Configuration")

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

log_area = st.empty()

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
        logging.error(f"Failed to initialize {name}: {e}")
        st.warning(f"{name.capitalize()} unavailable. Check API keys or try another exchange.")
        return None

def get_price(ex, sym):
    try:
        t = ex.fetch_ticker(sym)
        return t["last"]
    except Exception as e:
        logging.error(f"Failed to fetch price for {sym} on {ex.id}: {e}")
        return None

def execute_trade(ex, side, symbol, amount, price):
    try:
        order = ex.create_order(symbol, 'limit', side, amount, price)
        return order
    except Exception as e:
        logging.error(f"Trade execution failed: {e}")
        return None

# ------------------------------------------
# MAIN LOOP
# ------------------------------------------
if perform:
    st.session_state.armed = True
    st.session_state.stop = False
    st.success("⚙️ Bot armed — scanning for profitable signals...")

if stop:
    st.session_state.armed = False
    st.session_state.stop = True
    st.warning("⛔ Bot stopped manually.")

if st.session_state.armed and not st.session_state.stop:
    buy = create_exchange(buy_ex, buy_api_key, buy_secret)
    sell = create_exchange(sell_ex, sell_api_key, sell_secret)

    if not buy or not sell:
        st.error("Exchange initialization failed. Ensure API keys are correct or switch exchanges.")
    else:
        if symbol not in buy.markets or symbol not in sell.markets:
            st.error(f"Pair '{symbol}' not available on one or both exchanges.")
            st.session_state.armed = False
        else:
            pb = get_price(buy, symbol)
            ps = get_price(sell, symbol)
            if pb and ps:
                diff = ((ps - pb) / pb) * 100
                profit = investment * (diff / 100)
                colx, coly, colz = st.columns(3)
                with colx:
                    st.markdown(f"<div class='metric-green'><h4>Buy @ {buy_ex.capitalize()}</h4><p>${pb:.2f}</p></div>", unsafe_allow_html=True)
                with coly:
                    st.markdown(f"<div class='metric-red'><h4>Sell @ {sell_ex.capitalize()}</h4><p>${ps:.2f}</p></div>", unsafe_allow_html=True)
                with colz:
                    st.markdown(f"<div class='metric-profit'><h4>Profit</h4><p>${profit:.2f} ({diff:.2f}%)</p></div>", unsafe_allow_html=True)

                if diff >= threshold:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if sim:
                        st.success(f"🚀 PROFIT DETECTED (SIMULATION): +${profit:.2f} ({diff:.2f}%) — simulated trade executed.")
                        st.session_state.log.append(f"{timestamp}: Simulated trade: +${profit:.2f} ({diff:.2f}%)")
                    else:
                        amount = investment / pb
                        buy_order = execute_trade(buy, 'buy', symbol, amount, pb)
                        sell_order = execute_trade(sell, 'sell', symbol, amount, ps)
                        if buy_order and sell_order:
                            st.success(f"🚀 PROFIT DETECTED: Real trade executed! +${profit:.2f} ({diff:.2f}%)")
                            st.session_state.log.append(f"{timestamp}: Real trade executed: +${profit:.2f} ({diff:.2f}%)")
                        else:
                            st.error("Real trade failed. Check balances and permissions.")
                    st.session_state.armed = False
                else:
                    st.info(f"Monitoring... Diff: {diff:.2f}% (< {threshold}%)")
            else:
                st.warning("Price unavailable on one or both exchanges.")
    time.sleep(3)
    st.rerun()

# ------------------------------------------
# TRADE HISTORY
# ------------------------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("📜 Recent Trades History")
if st.session_state.log:
    st.write("\n".join(st.session_state.log[-20:]))
else:
    st.info("No trades yet. Click ▶️ Perform to start monitoring.")
st.markdown('</div>', unsafe_allow_html=True)
