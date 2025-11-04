import ccxt
import streamlit as st
import time
import logging
import datetime
import pandas as pd

# ------------------------------------------
# BASIC CONFIG
# ------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")

EXCHANGES = ccxt.exchanges

# Common crypto pairs for selectbox
COMMON_CRYPTOS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "SOL/USDT", 
    "XRP/USDT", "DOT/USDT", "DOGE/USDT", "LTC/USDT", "LINK/USDT",
    "MATIC/USDT", "AVAX/USDT", "UNI/USDT", "ALGO/USDT", "VET/USDT",
    "ICP/USDT", "FIL/USDT", "TRX/USDT", "ETC/USDT", "XLM/USDT",
    "Custom"  # Add this for custom input
]

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
# CUSTOM STYLE — ENHANCED MATURE GRAPHICS
# ------------------------------------------
st.markdown("""
<style>
body {
    background: linear-gradient(135deg, #000000, #1a1a1a);
    color: #ffffff;
    font-family: "Segoe UI", sans-serif;
    overflow-x: hidden;
    animation: globalFade 1.5s ease-in;
}

@keyframes globalFade {
    from { opacity: 0; transform: scale(0.98); }
    to { opacity: 1; transform: scale(1); }
}

/* Trishul background with enhanced glow and particles */
div[data-testid="stAppViewContainer"] {
    background: url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg') no-repeat center center fixed;
    background-size: 600px 600px;
    background-blend-mode: soft-light;
    opacity: 0.98;
    background-color: #000000;
    box-shadow: inset 0 0 150px rgba(255,215,0,0.15);
    position: relative;
}

div[data-testid="stAppViewContainer"]::before {
    content: "";
    background: url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg') no-repeat center center;
    background-size: 650px 650px;
    opacity: 0.07;
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 100%;
    height: 100%;
    z-index: 0;
    pointer-events: none;
    filter: drop-shadow(0 0 30px rgba(255,215,0,0.4)) blur(1px);
}

div[data-testid="stAppViewContainer"]::after {
    content: "";
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: radial-gradient(circle at 20% 80%, rgba(255,215,0,0.1) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(255,215,0,0.1) 0%, transparent 50%);
    z-index: -1;
    animation: particleFloat 10s infinite linear;
}

@keyframes particleFloat {
    0% { transform: translateY(0px); }
    100% { transform: translateY(-20px); }
}

/* Title with advanced glow and rotation */
h1 {
    color: #FFD700;
    text-align: center;
    font-weight: 800;
    text-shadow: 0 0 40px rgba(255,215,0,1), 0 0 80px rgba(255,215,0,0.6), 0 0 120px rgba(255,215,0,0.3);
    margin-bottom: 15px;
    animation: titleGlow 4s infinite ease-in-out, titleRotate 20s infinite linear;
}

@keyframes titleGlow {
    0%, 100% { text-shadow: 0 0 40px rgba(255,215,0,1); }
    50% { text-shadow: 0 0 60px rgba(255,215,0,1.2); }
}

@keyframes titleRotate {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* Panels with 3D effects and slide-in */
.block {
    background: linear-gradient(145deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05));
    border-radius: 20px;
    padding: 25px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5), 0 0 40px rgba(255,215,0,0.2), inset 0 1px 0 rgba(255,255,255,0.1);
    margin-bottom: 30px;
    z-index: 1;
    animation: blockSlide 0.8s ease-out;
    border: 1px solid rgba(255,215,0,0.1);
}

@keyframes blockSlide {
    from { transform: translateY(30px) scale(0.95); opacity: 0; }
    to { transform: translateY(0) scale(1); opacity: 1; }
}

/* Metric cards with 3D depth and hover rotations */
.metric-green {
    background: linear-gradient(145deg, rgba(0,255,0,0.2), rgba(0,255,0,0.1));
    padding: 20px;
    border-radius: 15px;
    border-left: 5px solid #00ff00;
    box-shadow: 0 5px 15px rgba(0,255,0,0.4), inset 0 1px 0 rgba(255,255,255,0.2);
    transition: all 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    transform-style: preserve-3d;
}

.metric-green:hover {
    transform: rotateX(5deg) rotateY(5deg) scale(1.03);
    box-shadow: 0 10px 25px rgba(0,255,0,0.6);
}

.metric-red {
    background: linear-gradient(145deg, rgba(255,0,0,0.2), rgba(255,0,0,0.1));
    padding: 20px;
    border-radius: 15px;
    border-left: 5px solid #ff0000;
    box-shadow: 0 5px 15px rgba(255,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.2);
    transition: all 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    transform-style: preserve-3d;
}

.metric-red:hover {
    transform: rotateX(5deg) rotateY(5deg) scale(1.03);
    box-shadow: 0 10px 25px rgba(255,0,0,0.6);
}

.metric-profit {
    background: linear-gradient(145deg, rgba(255,215,0,0.15), rgba(255,215,0,0.08));
    padding: 20px;
    border-radius: 15px;
    border-left: 5px solid #FFD700;
    box-shadow: 0 5px 15px rgba(255,215,0,0.5), inset 0 1px 0 rgba(255,255,255,0.2);
    transition: all 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    transform-style: preserve-3d;
}

.metric-profit:hover {
    transform: rotateX(5deg) rotateY(5deg) scale(1.03);
    box-shadow: 0 10px 25px rgba(255,215,0,0.7);
}

/* Buttons with advanced hover and depth */
.stButton>button {
    background: linear-gradient(145deg, #FFD700, #b8860b, #FFD700);
    color: #000;
    border: none;
    border-radius: 10px;
    padding: 15px 25px;
    font-size: 16px;
    font-weight: 600;
    transition: all 0.4s ease;
    box-shadow: 0 5px 15px rgba(255,215,0,0.4), inset 0 1px 0 rgba(255,255,255,0.3);
    position: relative;
    overflow: hidden;
}

.stButton>button::before {
    content: "";
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
    transition: left 0.5s;
}

.stButton>button:hover::before {
    left: 100%;
}

.stButton>button:hover {
    background: linear-gradient(145deg, #ffcc33, #d4af37, #ffcc33);
    transform: translateY(-3px) scale(1.05);
    box-shadow: 0 10px 25px rgba(255,215,0,0.6);
}

/* Inputs with refined glow and focus */
.stSelectbox, .stTextInput, .stNumberInput {
    border-radius: 8px;
    background: linear-gradient(145deg, rgba(255,255,255,0.08), rgba(255,255,255,0.04));
    border: 1px solid rgba(255,215,0,0.3);
    transition: all 0.3s ease;
    box-shadow: inset 0 2px 5px rgba(0,0,0,0.2);
}

.stSelectbox:focus, .stTextInput:focus, .stNumberInput:focus {
    border-color: #FFD700;
    box-shadow: 0 0 10px rgba(255,215,0,0.5), inset 0 2px 5px rgba(0,0,0,0.2);
}

/* Subheaders with clean styling */
h2, h3, h4 {
    color: #FFD700;
    font-weight: 600;
    margin-bottom: 10px;
}

/* Chart container with depth */
.chart-container {
    background: linear-gradient(145deg, rgba(255,255,255,0.08), rgba(255,255,255,0.04));
    border-radius: 15px;
    padding: 15px;
    margin-top: 15px;
    box-shadow: 0 5px 15px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.1);
    border: 1px solid rgba(255,215,0,0.2);
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
if "price_history" not in st.session_state:
    st.session_state.price_history = {"buy": [], "sell": [], "diff": []}

# ------------------------------------------
# INPUT UI
# ------------------------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Configuration")

col1, col2 = st.columns(2)
with col1:
    buy_ex = st.selectbox("Buy Exchange", EXCHANGES, index=0)
    buy_api_key = st.text_input(f"{buy_ex.capitalize()} API Key", type="password", key="buy_key")
    buy_secret = st.text_input(f"{buy_ex.capitalize()} Secret Key", type="password", key="buy_secret")
with col2:
    sell_ex = st.selectbox("Sell Exchange", EXCHANGES, index=1)
    sell_api_key = st.text_input(f"{sell_ex.capitalize()} API Key", type="password", key="sell_key")
    sell_secret = st.text_input(f"{sell_ex.capitalize()} Secret Key", type="password", key="sell_secret")

# Crypto pair selection with selectbox and custom option
symbol_choice = st.selectbox("Crypto Pair", COMMON_CRYPTOS, index=0)
if symbol_choice == "Custom":
    symbol = st.text_input("Enter Custom Pair (e.g., BTC/USDT, ETH/BTC)", value="BTC/USDT")
else:
    symbol = symbol_choice

investment = st.number_input("Investment ($)", min_value=1.0, value=1000.0, step=1.0)
threshold = st.slider("Profit Threshold (%)", 0.1, 10.0, 1.0)

# Profit Preview Section
st.subheader("Profit Preview")
preview_buy = create_exchange(buy_ex)
preview_sell = create_exchange(sell_ex)
if preview_buy and preview_sell:
    if symbol in preview_buy.markets and symbol in preview_sell.markets:
        pb_preview = get_price(preview_buy, symbol)
        ps_preview = get_price(preview_sell, symbol)
        if pb_preview and ps_preview:
            diff_preview = ((ps_preview - pb_preview) / pb_preview) * 100
            profit_preview = investment * (diff_preview / 100)
            col_prev = st.columns(3)
            with col_prev[0]:
                st.metric("Buy Price", f"${pb_preview:.2f}")
            with col_prev[1]:
                st.metric("Sell Price", f"${ps_preview:.2f}")
            with col_prev[2]:
                st.metric("Potential Profit", f"${profit_preview:.2f} ({diff_preview:.2f}%)")
        else:
            st.warning("Unable to fetch preview prices.")
    else:
        st.warning("Pair not available on selected exchanges for preview.")
else:
    st.warning("Exchange preview unavailable.")

colA, colB = st.columns(2)
with colA:
    perform = st.button("Perform")
with colB:
    stop = st.button("Stop")

sim = st.checkbox("Simulation Mode", True)
st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------
# LIVE MONITORING SECTION
# ------------------------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Live Monitoring")

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
                
                # Update history for chart
                st.session_state.price_history["buy"].append(pb)
                st.session_state.price_history["sell"].append(ps)
                st.session_state.price_history["diff"].append(diff)
                if len(st.session_state.price_history["buy"]) > 50:  # Keep last 50 points
                    st.session_state.price_history["buy"].pop(0)
                    st.session_state.price_history["sell"].pop(0)
                    st.session_state.price_history["diff"].pop(0)
                
                colx, coly, colz = st.columns(3)
                with colx:
                    st.markdown(f"<div class='metric-green'><h4>Buy @ {buy_ex.capitalize()}</h4><p>${pb:.2f}</p></div>", unsafe_allow_html=True)
                with coly:
                    st.markdown(f"<div class='metric-red'><h4>Sell @ {sell_ex.capitalize()}</h4><p>${ps:.2f}</p></div>", unsafe_allow_html=True)
                with colz:
                    st.markdown(f"<div class='metric-profit'><h4>Profit</h4><p>${profit:.2f} ({diff:.2f}%)</p></div>", unsafe_allow_html=True)

                # Chart using Streamlit's built-in line chart
                if st.session_state.price_history["buy"]:
                    df = pd.DataFrame({
                        "Buy Price": st.session_state.price_history["buy"],
                        "Sell Price": st.session_state.price_history["sell"],
                        "Diff %": st.session_state.price