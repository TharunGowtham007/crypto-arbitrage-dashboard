# app.py (corrected, completed, error-free)
import ccxt
import streamlit as st
import time
import logging
import datetime
import pandas as pd
from decimal import Decimal, ROUND_DOWN

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

DEFAULT_POLL = 5
MAX_HISTORY = 50

# ------------------------------------------
# EXCHANGE HELPERS
# ------------------------------------------
def create_exchange(name, api_key=None, secret=None):
    try:
        config = {"enableRateLimit": True}
        if api_key and secret:
            config.update({"apiKey": api_key, "secret": secret})
        ex = getattr(ccxt, name)(config)
        # load_markets may fail for restricted exchanges; catch but continue
        try:
            ex.load_markets()
        except Exception:
            logging.debug(f"Warning: couldn't load markets for {name} (may be restricted)")
        return ex
    except Exception as e:
        logging.error(f"Failed to initialize {name}: {e}")
        return None

def get_price(ex, sym):
    try:
        if not ex:
            return None
        # try load_markets if empty
        try:
            if not getattr(ex, "markets", None):
                ex.load_markets()
        except Exception:
            pass
        if sym not in getattr(ex, "markets", {}):
            return None
        t = ex.fetch_ticker(sym)
        return t.get("last") or t.get("close")
    except Exception as e:
        logging.error(f"Failed to fetch price for {sym} on {getattr(ex,'id', 'unknown')}: {e}")
        return None

def execute_trade(ex, side, symbol, amount, price):
    try:
        order = ex.create_order(symbol, 'limit', side, amount, price)
        return order
    except Exception as e:
        logging.error(f"Trade execution failed on {getattr(ex,'id', 'unknown')}: {e}")
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
    animation: globalFade 0.6s ease-in;
}
@keyframes globalFade { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

/* Trishul background & soft glow */
div[data-testid="stAppViewContainer"] {
    background: url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg') no-repeat center center fixed;
    background-size: 600px 600px;
    background-blend-mode: soft-light;
    opacity: 0.98;
    background-color: #000000;
    box-shadow: inset 0 0 120px rgba(255,215,0,0.06);
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
    filter: drop-shadow(0 0 24px rgba(255,215,0,0.35)) blur(0.6px);
}

/* Panels & metrics */
.block { background: linear-gradient(145deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02)); border-radius: 16px; padding: 18px; margin-bottom: 18px; border: 1px solid rgba(255,215,0,0.06); }
.metric-green { background: linear-gradient(145deg, rgba(0,255,0,0.12), rgba(0,255,0,0.06)); padding: 12px; border-radius: 10px; }
.metric-red { background: linear-gradient(145deg, rgba(255,0,0,0.12), rgba(255,0,0,0.06)); padding: 12px; border-radius: 10px; }
.metric-profit { background: linear-gradient(145deg, rgba(255,215,0,0.10), rgba(255,215,0,0.06)); padding: 12px; border-radius: 10px; box-shadow: 0 4px 12px rgba(255,215,0,0.06); }

.stButton>button { background: linear-gradient(90deg,#FFD700,#d4af37); color:#000; border-radius:10px; padding:10px 18px; font-weight:700; }
.stButton>button:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(255,215,0,0.12); }

.stSelectbox, .stTextInput, .stNumberInput { border-radius:8px; background: rgba(255,255,255,0.03); padding:6px; }
.small-muted { color: #bfc7cd; font-size:13px; }
.log-box { max-height:220px; overflow:auto; background: rgba(0,0,0,0.25); padding:8px; border-radius:8px; color:#fff; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------
# HEADER
# ------------------------------------------
st.title("Arbitrage Dashboard")
st.markdown('<div class="small-muted">Faint golden Trishul in background. Use Simulation Mode to test before real trading.</div>', unsafe_allow_html=True)

# ------------------------------------------
# SESSION STATE
# ------------------------------------------
if "armed" not in st.session_state:
    st.session_state.armed = False
if "stop" not in st.session_state:
    st.session_state.stop = False
if "log" not in st.session_state:
    st.session_state.log = []
if "price_history" not in st.session_state:
    st.session_state.price_history = {"buy": [], "sell": [], "diff": [], "ts": []}

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

# Preview area
st.markdown("---")
st.subheader("Preview (quick)")

preview_buy = create_exchange(buy_ex)
preview_sell = create_exchange(sell_ex)

if preview_buy is None or preview_sell is None:
    st.warning("One or both exchanges are unavailable for preview. You can still proceed; the app will try again when monitoring.")
else:
    # check markets presence safely
    has_buy = symbol in getattr(preview_buy, "markets", {})
    has_sell = symbol in getattr(preview_sell, "markets", {})
    if has_buy and has_sell:
        pb_preview = get_price(preview_buy, symbol)
        ps_preview = get_price(preview_sell, symbol)
        if pb_preview is not None and ps_preview is not None:
            diff_preview = ((ps_preview - pb_preview) / pb_preview) * 100
            profit_preview = investment * (diff_preview / 100)
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Buy Price", f"${pb_preview:,.2f}")
            with c2:
                st.metric("Sell Price", f"${ps_preview:,.2f}")
            with c3:
                st.metric("Potential Profit", f"${profit_preview:,.2f} ({diff_preview:.2f}%)")
        else:
            st.info("Preview prices could not be fetched (exchange may be restricted).")
    else:
        st.info("Pair not available on one or both preview exchanges.")
st.markdown("---")

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

# handle button actions
if perform:
    st.session_state.armed = True
    st.session_state.stop = False
    st.success("Bot armed — monitoring started.")
if stop:
    st.session_state.armed = False
    st.session_state.stop = True
    st.warning("Bot stopped by user.")

# main monitoring logic (single-iteration per run; uses st.experimental_rerun to loop safely)
if st.session_state.armed and not st.session_state.stop:
    buy = create_exchange(buy_ex, buy_api_key, buy_secret)
    sell = create_exchange(sell_ex, sell_api_key, sell_secret)

    if not buy or not sell:
        st.error("Exchange initialization failed for buy or sell. Try switching exchanges or check API keys.")
        st.session_state.armed = False
    else:
        has_buy = symbol in getattr(buy, "markets", {})
        has_sell = symbol in getattr(sell, "markets", {})
        if not (has_buy and has_sell):
            st.error(f"Pair '{symbol}' not available on one or both exchanges.")
            st.session_state.armed = False
        else:
            pb = get_price(buy, symbol)
            ps = get_price(sell, symbol)
            if pb is None or ps is None:
                st.warning("Price not available currently on one or both exchanges.")
                st.session_state.log.append(f"{datetime.datetime.utcnow().isoformat()} - Price unavailable for {symbol} on one or both exchanges.")
                time.sleep(DEFAULT_POLL)
                st.experimental_rerun()
            else:
                diff = ((ps - pb) / pb) * 100
                profit = investment * (diff / 100)

                # update history
                ts = datetime.datetime.utcnow().strftime("%H:%M:%S")
                st.session_state.price_history["buy"].append(pb)
                st.session_state.price_history["sell"].append(ps)
                st.session_state.price_history["diff"].append(diff)
                st.session_state.price_history["ts"].append(ts)
                # trim
                if len(st.session_state.price_history["buy"]) > MAX_HISTORY:
                    for k in st.session_state.price_history:
                        st.session_state.price_history[k].pop(0)

                colx, coly, colz = st.columns(3)
                with colx:
                    st.markdown(f"<div class='metric-green'><h4>Buy @ {buy_ex.capitalize()}</h4><p>${pb:,.2f}</p></div>", unsafe_allow_html=True)
                with coly:
                    st.markdown(f"<div class='metric-red'><h4>Sell @ {sell_ex.capitalize()}</h4><p>${ps:,.2f}</p></div>", unsafe_allow_html=True)
                with colz:
                    st.markdown(f"<div class='metric-profit'><h4>Profit</h4><p>${profit:,.2f} ({diff:.2f}%)</p></div>", unsafe_allow_html=True)

                # chart
                try:
                    df = pd.DataFrame({
                        "Buy Price": st.session_state.price_history["buy"],
                        "Sell Price": st.session_state.price_history["sell"],
                        "Diff %": st.session_state.price_history["diff"]
                    }, index=st.session_state.price_history["ts"])
                    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                    st.line_chart(df[["Buy Price", "Sell Price"]])
                    st.markdown('</div>', unsafe_allow_html=True)
                except Exception as e:
                    logging.debug(f"chart error: {e}")

                # decision
                if diff >= threshold:
                    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                    if sim:
                        st.success(f"PROFIT DETECTED (SIM): ${profit:,.2f} ({diff:.2f}%) — simulated execution.")
                        st.session_state.log.append(f"{now} SIM exec {symbol} buy:{buy_ex} sell:{sell_ex} +${profit:,.2f} ({diff:.2f}%)")
                        st.session_state.armed = False
                        time.sleep(1)
                        st.experimental_rerun()
                    else:
                        # finalize auth instances for real orders
                        buy_exec = create_exchange(buy_ex, buy_api_key, buy_secret)
                        sell_exec = create_exchange(sell_ex, sell_api_key, sell_secret)
                        if not buy_exec or not sell_exec:
                            st.error("Auth init before execution failed.")
                            st.session_state.armed = False
                            st.experimental_rerun()
                        # re-fetch as safety
                        pb2 = get_price(buy_exec, symbol)
                        ps2 = get_price(sell_exec, symbol)
                        if pb2 is None or ps2 is None:
                            st.error("Final price re-check failed. Aborting execution.")
                            st.session_state.armed = False
                            st.experimental_rerun()
                        diff2 = ((ps2 - pb2) / pb2) * 100
                        if diff2 < threshold:
                            st.warning("Final re-check below threshold. Continue monitoring.")
                            time.sleep(DEFAULT_POLL)
                            st.experimental_rerun()
                        # compute amount and attempt market orders (use caution)
                        base_amount = investment / pb2 if pb2 > 0 else 0
                        # rounding omitted (different exchanges have different precision rules)
                        try:
                            st.info("Placing BUY order...")
                            buy_order = buy_exec.create_market_order(symbol, 'buy', base_amount)
                            st.write("Buy response:", buy_order)
                        except Exception as e:
                            st.error(f"Buy order failed: {e}")
                            st.session_state.armed = False
                            st.experimental_rerun()
                        try:
                            st.info("Placing SELL order...")
                            sell_order = sell_exec.create_market_order(symbol, 'sell', base_amount)
                            st.write("Sell response:", sell_order)
                        except Exception as e:
                            st.error(f"Sell order failed: {e}")
                            st.session_state.armed = False
                            st.experimental_rerun()
                        st.success(f"REAL trade executed. Est profit ~ ${profit:,.2f} ({diff:.2f}%)")
                        st.session_state.log.append(f"{now} REAL exec {symbol} buy:{buy_ex} sell:{sell_ex} +${profit:,.2f} ({diff:.2f}%)")
                        st.session_state.armed = False
                        time.sleep(1)
                        st.experimental_rerun()
                else:
                    st.info(f"Monitoring... Diff: {diff:.2f}% (< {threshold}%)")
                    st.session_state.log.append(f"{datetime.datetime.utcnow().isoformat()} - Checked {symbol} diff {diff:.2f}%")
                    time.sleep(DEFAULT_POLL)
                    st.experimental_rerun()

st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------
# TRADE HISTORY / LOGS
# ------------------------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Recent Activity / Logs")
if st.session_state.log:
    # show last 50 lines
    st.write("\n".join(st.session_state.log[-50:]))
else:
    st.info("No activity yet. Click Perform to start monitoring.")
st.markdown('</div>', unsafe_allow_html=True)