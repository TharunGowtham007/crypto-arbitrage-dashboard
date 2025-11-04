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

COMMON_CRYPTOS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "SOL/USDT",
    "XRP/USDT", "DOT/USDT", "DOGE/USDT", "LTC/USDT", "LINK/USDT",
    "MATIC/USDT", "AVAX/USDT", "UNI/USDT", "ALGO/USDT", "VET/USDT",
    "ICP/USDT", "FIL/USDT", "TRX/USDT", "ETC/USDT", "XLM/USDT",
    "Custom"
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
# CUSTOM STYLE — MINIMAL & MATURE GOLDEN THEME
# ------------------------------------------
st.markdown("""
<style>
body {
    background-color: #0a0a0a;
    color: #e6e6e6;
    font-family: "Segoe UI", sans-serif;
}

div[data-testid="stAppViewContainer"] {
    background: #0a0a0a url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg') 
                no-repeat center center fixed;
    background-size: 650px 650px;
    background-blend-mode: soft-light;
    opacity: 0.98;
}

div[data-testid="stAppViewContainer"]::before {
    content: "";
    background: url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg') 
                no-repeat center center;
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
    filter: drop-shadow(0 0 15px rgba(255,215,0,0.3));
}

/* Title */
h1 {
    color: #FFD700;
    text-align: center;
    font-weight: 800;
    text-shadow: 0 0 30px rgba(255,215,0,0.4);
    margin-bottom: 15px;
}

/* Panels */
.block {
    background: rgba(255,255,255,0.05);
    border-radius: 15px;
    padding: 20px;
    box-shadow: 0 0 20px rgba(255,215,0,0.15);
    margin-bottom: 25px;
    z-index: 1;
}

/* Metric cards */
.metric-green {
    background: linear-gradient(135deg, rgba(0,255,0,0.1), rgba(0,255,0,0.05));
    padding: 15px;
    border-radius: 10px;
    border-left: 4px solid #00ff00;
    box-shadow: 0 0 10px rgba(0,255,0,0.2);
}

.metric-red {
    background: linear-gradient(135deg, rgba(255,0,0,0.1), rgba(255,0,0,0.05));
    padding: 15px;
    border-radius: 10px;
    border-left: 4px solid #ff0000;
    box-shadow: 0 0 10px rgba(255,0,0,0.2);
}

.metric-profit {
    background: linear-gradient(135deg, rgba(255,215,0,0.08), rgba(255,215,0,0.03));
    padding: 15px;
    border-radius: 10px;
    border-left: 4px solid #FFD700;
    box-shadow: 0 0 10px rgba(255,215,0,0.25);
}

/* Buttons */
.stButton>button {
    background: linear-gradient(135deg, #FFD700, #b8860b);
    color: #000;
    border: none;
    border-radius: 8px;
    padding: 12px 22px;
    font-size: 16px;
    font-weight: 600;
    box-shadow: 0 4px 10px rgba(255,215,0,0.3);
    transition: all 0.3s ease;
}

.stButton>button:hover {
    background: linear-gradient(135deg, #ffcc33, #d4af37);
    transform: scale(1.03);
    box-shadow: 0 6px 20px rgba(255,215,0,0.5);
}

/* Inputs */
.stSelectbox, .stTextInput, .stNumberInput {
    border-radius: 5px;
    background-color: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,215,0,0.2);
}

.chart-container {
    background: rgba(255,255,255,0.05);
    border-radius: 10px;
    padding: 10px;
    box-shadow: 0 0 10px rgba(255,215,0,0.15);
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

symbol_choice = st.selectbox("Crypto Pair", COMMON_CRYPTOS, index=0)
symbol = st.text_input("Enter Custom Pair", "BTC/USDT") if symbol_choice == "Custom" else symbol_choice

investment = st.number_input("Investment ($)", min_value=1.0, value=1000.0, step=1.0)
threshold = st.slider("Profit Threshold (%)", 0.1, 10.0, 1.0)

colA, colB = st.columns(2)
with colA:
    perform = st.button("Perform")
with colB:
    stop = st.button("Stop")

sim = st.checkbox("Simulation Mode", True)
st.markdown('</div>', unsafe_allow_html=True)


# ------------------------------------------
# LIVE MONITORING
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

                st.session_state.price_history["buy"].append(pb)
                st.session_state.price_history["sell"].append(ps)
                st.session_state.price_history["diff"].append(diff)
                if len(st.session_state.price_history["buy"]) > 50:
                    for k in ["buy", "sell", "diff"]:
                        st.session_state.price_history[k].pop(0)

                colx, coly, colz = st.columns(3)
                with colx:
                    st.markdown(f"<div class='metric-green'><h4>Buy @ {buy_ex.capitalize()}</h4><p>${pb:.2f}</p></div>", unsafe_allow_html=True)
                with coly:
                    st.markdown(f"<div class='metric-red'><h4>Sell @ {sell_ex.capitalize()}</h4><p>${ps:.2f}</p></div>", unsafe_allow_html=True)
                with colz:
                    st.markdown(f"<div class='metric-profit'><h4>Profit</h4><p>${profit:.2f} ({diff:.2f}%)</p></div>", unsafe_allow_html=True)

                if st.session_state.price_history["buy"]:
                    df = pd.DataFrame({
                        "Buy Price": st.session_state.price_history["buy"],
                        "Sell Price": st.session_state.price_history["sell"],
                        "Diff %": st.session_state.price_history["diff"]
                    })
                    st.line_chart(df, use_container_width=True)

                if diff >= threshold:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if sim:
                        st.success(f"Profit detected (Simulation): +${profit:.2f} ({diff:.2f}%) — simulated trade executed.")
                        st.session_state.log.append(f"{timestamp}: Simulated trade: +${profit:.2f} ({diff:.2f}%)")
                    else:
                        amount = investment / pb
                        buy_order = execute_trade(buy, 'buy', symbol, amount, pb)
                        sell_order = execute_trade(sell, 'sell', symbol, amount, ps)
                        if buy_order and sell_order:
                            st.success(f"Profit detected: Real trade executed! +${profit:.2f} ({diff:.2f}%)")
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
else:
    st.info("Click Perform to start monitoring.")
st.markdown('</div>', unsafe_allow_html=True)


# ------------------------------------------
# TRADE HISTORY
# ------------------------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Recent Trades History")
if st.session_state.log:
    st.write("\n".join(st.session_state.log[-20:]))
else:
    st.info("No trades yet. Click Perform to start monitoring.")
st.markdown('</div>', unsafe_allow_html=True)


# ------------------------------------------
# TRIGGER
# ------------------------------------------
if perform:
    st.session_state.armed = True
    st.session_state.stop = False
    st.success("Bot armed — scanning for profitable signals...")

if stop:
    st.session_state.armed = False
    st.session_state.stop = True
    st.warning("Bot stopped manually.")
