import ccxt
import streamlit as st
import time
import logging
import datetime

# ------------------------------------------
# BASIC CONFIG
# ------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")

EXCHANGES = ccxt.exchanges

# ------------------------------------------
# STYLE — Glassmorphic + Golden Theme
# ------------------------------------------
st.markdown("""
<style>
/* Background */
body, div[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at center, #0d0d0d 0%, #000000 100%);
    color: #f8f9fa;
    font-family: "Segoe UI", sans-serif;
}

/* Trishul watermark */
body::before {
    content: "🔱";
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 600px;
    color: rgba(212,175,55,0.06);
    z-index: 0;
    pointer-events: none;
}

/* Glassmorphic block style */
.block {
    background: rgba(255, 255, 255, 0.08);
    border-radius: 15px;
    padding: 25px;
    box-shadow: 0 4px 30px rgba(0,0,0,0.5);
    backdrop-filter: blur(15px);
    -webkit-backdrop-filter: blur(15px);
    border: 1px solid rgba(255,255,255,0.1);
    margin-bottom: 25px;
    z-index: 2;
}

/* Centered Title */
h1 {
    text-align: center !important;
    font-size: 42px !important;
    color: #ffd700;
    text-shadow: 0px 0px 20px rgba(255,215,0,0.3);
}

/* Metric cards */
.metric-green { background-color: rgba(40,167,69,0.15); border-left: 4px solid #28a745; padding: 15px; border-radius: 10px; }
.metric-red { background-color: rgba(220,53,69,0.15); border-left: 4px solid #dc3545; padding: 15px; border-radius: 10px; }
.metric-profit { background-color: rgba(255,193,7,0.15); border-left: 4px solid #ffc107; padding: 15px; border-radius: 10px; }

/* Buttons */
.stButton>button {
    background: linear-gradient(145deg, #ffd700, #d4af37);
    color: #000;
    border: none;
    border-radius: 8px;
    padding: 10px 22px;
    font-size: 16px;
    font-weight: bold;
    box-shadow: 0 0 10px rgba(255,215,0,0.3);
    transition: 0.3s;
}
.stButton>button:hover {
    background: linear-gradient(145deg, #e0b646, #b7950b);
    box-shadow: 0 0 20px rgba(255,215,0,0.6);
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------
# HEADER
# ------------------------------------------
st.title("💎 ARBITRAGE DASHBOARD 💎")

# ------------------------------------------
# SESSION
# ------------------------------------------
if "armed" not in st.session_state:
    st.session_state.armed = False
if "stop" not in st.session_state:
    st.session_state.stop = False
if "log" not in st.session_state:
    st.session_state.log = []
if "pair_list" not in st.session_state:
    st.session_state.pair_list = []

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

def get_fee(ex, sym, side):
    try:
        market = ex.market(sym)
        maker_fee = market.get("maker", 0.001)
        taker_fee = market.get("taker", 0.001)
        return taker_fee if side == "sell" else maker_fee
    except Exception as e:
        logging.warning(f"Fee fetch failed for {ex.id}: {e}")
        return 0.001

# ------------------------------------------
# UI — CONFIGURATION
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

if st.button("🔄 Load Available Pairs"):
    buy = create_exchange(buy_ex, buy_api_key, buy_secret)
    sell = create_exchange(sell_ex, sell_api_key, sell_secret)
    if buy and sell:
        common_pairs = list(set(buy.symbols) & set(sell.symbols))
        if common_pairs:
            st.session_state.pair_list = sorted(common_pairs)
            st.success(f"Loaded {len(common_pairs)} common trading pairs.")
        else:
            st.warning("No common pairs found between selected exchanges.")
    else:
        st.error("Failed to load exchange data.")

if st.session_state.pair_list:
    symbol = st.selectbox("Crypto Pair", st.session_state.pair_list)
else:
    symbol = st.text_input("Crypto Pair (e.g., BTC/USDT)", value="BTC/USDT")

investment = st.number_input("Investment ($)", min_value=1.0, value=1000.0, step=1.0)
threshold = st.slider("Profit Threshold (%)", 1.0, 20.0, 3.0, step=0.5)

colA, colB = st.columns(2)
with colA:
    perform = st.button("▶️ Perform")
with colB:
    stop = st.button("⛔ Stop")

sim = st.checkbox("Simulation Mode (Safe Mode)", True)
st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------
# SAFE TRADE EXECUTION
# ------------------------------------------
def execute_trade(buy_ex_obj, sell_ex_obj, symbol, amount):
    try:
        buy_balance = buy_ex_obj.fetch_balance()
        sell_balance = sell_ex_obj.fetch_balance()

        base, quote = symbol.split('/')
        if quote not in buy_balance['total'] or buy_balance['total'][quote] < amount * buy_ex_obj.fetch_ticker(symbol)['last']:
            st.error(f"Insufficient {quote} balance on {buy_ex_obj.id} for buying.")
            return None, None
        if base not in sell_balance['total']:
            st.error(f"No {base} balance found on {sell_ex_obj.id} for selling.")
            return None, None

        confirm = st.warning("⚠️ Confirm Trade Execution? This will perform a REAL transaction.")
        confirm_btn = st.button("✅ Confirm Real Trade Execution")

        if confirm_btn:
            buy_order = buy_ex_obj.create_market_buy_order(symbol, amount)
            sell_order = sell_ex_obj.create_market_sell_order(symbol, amount)
            return buy_order, sell_order
        else:
            st.info("Trade cancelled by user.")
            return None, None

    except Exception as e:
        st.error(f"Trade execution failed: {e}")
        return None, None

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
        st.session_state.armed = False
    elif not symbol:
        st.error("No symbol selected.")
        st.session_state.armed = False
    else:
        pb = get_price(buy, symbol)
        ps = get_price(sell, symbol)
        if not pb or not ps or pb <= 0 or ps <= 0:
            st.warning("Invalid or unavailable prices.")
        else:
            buy_fee = get_fee(buy, symbol, "buy")
            sell_fee = get_fee(sell, symbol, "sell")
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

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if net_diff <= 0:
                st.warning("⚠️ Loss detected — stopped automatically.")
                st.session_state.armed = False

            elif net_diff >= threshold:
                if sim:
                    st.success(f"SIM PROFIT: +${profit:.2f} ({net_diff:.2f}%)")
                    st.session_state.log.append(f"{timestamp}: Simulated +${profit:.2f}")
                else:
                    st.warning("💥 PROFITABLE SIGNAL DETECTED! Ready to Execute.")
                    base_currency = symbol.split('/')[0]
                    amount = investment / pb
                    buy_order, sell_order = execute_trade(buy, sell, symbol, amount)
                    if buy_order and sell_order:
                        st.success(f"✅ REAL TRADE SUCCESS\nBought on {buy_ex}, Sold on {sell_ex}")
                        st.session_state.log.append(f"{timestamp}: Real trade executed for {symbol}, profit est. ${profit:.2f}")
                    else:
                        st.info("Trade skipped or cancelled.")
                st.session_state.armed = False
            else:
                st.info(f"📡 Monitoring... Diff: {net_diff:.2f}% (< {threshold}%)")

    if st.session_state.armed:
        time.sleep(5)
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
