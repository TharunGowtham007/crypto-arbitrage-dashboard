import ccxt
import streamlit as st
import time
import logging
import datetime
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# ------------------------------------------
# LOAD CONFIG FOR AUTHENTICATION
# ------------------------------------------
import os
print("Current working directory:", os.getcwd())
print("Files in this directory:", os.listdir())

import os
if not os.path.exists('config.yaml'):
    raise FileNotFoundError(f"config.yaml not found in: {os.getcwd()} \nFiles: {os.listdir()}")

with open(r"C:\Users\lenovo\OneDrive\CryptoArbitrage\config.yaml") as file:

    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)


# ------------------------------------------
# BASIC CONFIG
# ------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
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
div[data-testid="stAppViewContainer"] > .main {
    position: relative;
    z-index: 1;
}
.block {
    background: rgba(255,255,255,0.05);
    border-radius: 10px;
    padding: 20px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.3);
    margin-bottom: 20px;
    z-index: 2;
}
.metric-green { background-color: rgba(40,167,69,0.15); border-left: 4px solid #28a745; padding: 15px; border-radius: 8px; }
.metric-red { background-color: rgba(220,53,69,0.15); border-left: 4px solid #dc3545; padding: 15px; border-radius: 8px; }
.metric-profit { background-color: rgba(255,193,7,0.15); border-left: 4px solid #ffc107; padding: 15px; border-radius: 8px; }
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
</style>
""", unsafe_allow_html=True)

# ------------------------------------------
# AUTHENTICATION
# ------------------------------------------
name, authentication_status, username = authenticator.login('Login', 'main')

if authentication_status:
    # User is logged in - show the dashboard
    st.sidebar.title(f"Welcome, {name}!")
    authenticator.logout('Logout', 'sidebar')
    
    # ------------------------------------------
    # USER-SPECIFIC SESSION STATE
    # ------------------------------------------
    user_key = username  # Use username as key for user-specific data
    if f"armed_{user_key}" not in st.session_state:
        st.session_state[f"armed_{user_key}"] = False
    if f"stop_{user_key}" not in st.session_state:
        st.session_state[f"stop_{user_key}"] = False
    if f"log_{user_key}" not in st.session_state:
        st.session_state[f"log_{user_key}"] = []
    if f"pair_list_{user_key}" not in st.session_state:
        st.session_state[f"pair_list_{user_key}"] = []

    # ------------------------------------------
    # HEADER
    # ------------------------------------------
    st.title("Arbitrage Dashboard")

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
    # INPUT UI
    # ------------------------------------------
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.subheader("Configuration")

    col1, col2 = st.columns(2)
    with col1:
        buy_ex = st.selectbox("Buy Exchange", EXCHANGES, index=0, key=f"buy_ex_{user_key}")
        buy_api_key = st.text_input(f"{buy_ex.capitalize()} API Key", type="password", key=f"buy_key_{user_key}")
        buy_secret = st.text_input(f"{buy_ex.capitalize()} Secret", type="password", key=f"buy_secret_{user_key}")
    with col2:
        sell_ex = st.selectbox("Sell Exchange", EXCHANGES, index=1, key=f"sell_ex_{user_key}")
        sell_api_key = st.text_input(f"{sell_ex.capitalize()} API Key", type="password", key=f"sell_key_{user_key}")
        sell_secret = st.text_input(f"{sell_ex.capitalize()} Secret", type="password", key=f"sell_secret_{user_key}")

    # Load available pairs dynamically after exchanges are chosen
    if st.button("🔄 Load Available Pairs", key=f"load_pairs_{user_key}"):
        buy = create_exchange(buy_ex, buy_api_key, buy_secret)
        sell = create_exchange(sell_ex, sell_api_key, sell_secret)
        if buy and sell:
            # Intersect available pairs (common between both exchanges)
            common_pairs = list(set(buy.symbols) & set(sell.symbols))
            if common_pairs:
                st.session_state[f"pair_list_{user_key}"] = sorted(common_pairs)
                st.success(f"Loaded {len(common_pairs)} common trading pairs.")
            else:
                st.warning("No common pairs found between selected exchanges.")
        else:
            st.error("Failed to load exchange data.")

    if st.session_state[f"pair_list_{user_key}"]:
        symbol = st.selectbox("Crypto Pair", st.session_state[f"pair_list_{user_key}"], key=f"symbol_{user_key}")
    else:
        symbol = st.text_input("Crypto Pair (e.g., BTC/USDT)", value="BTC/USDT", key=f"symbol_text_{user_key}")

    investment = st.number_input("Investment ($)", min_value=1.0, value=1000.0, step=1.0, key=f"investment_{user_key}")
    threshold = st.slider("Profit Threshold (%)", 0.1, 10.0, 1.0, key=f"threshold_{user_key}")

    colA, colB = st.columns(2)
    with colA:
        perform = st.button("▶️ Perform", key=f"perform_{user_key}")
    with colB:
        stop = st.button("⛔ Stop", key=f"stop_btn_{user_key}")

    sim = st.checkbox("Simulation Mode", True, key=f"sim_{user_key}")
    st.markdown('</div>', unsafe_allow_html=True)

    # ------------------------------------------
    # MAIN LOGIC
    # ------------------------------------------
    if perform:
        st.session_state[f"armed_{user_key}"] = True
        st.session_state[f"stop_{user_key}"] = False
        st.success("Bot armed ✅ — waiting for profitable signal...")

    if stop:
        st.session_state[f"armed_{user_key}"] = False
        st.session_state[f"stop_{user_key}"] = True
        st.warning("Bot stopped ⛔")

    if st.session_state[f"armed_{user_key}"] and not st.session_state[f"stop_{user_key}"]:
        buy = create_exchange(buy_ex, buy_api_key, buy_secret)
        sell = create_exchange(sell_ex, sell_api_key, sell_secret)

        if not buy or not sell:
            st.error("Exchange initialization failed.")
            st.session_state[f"armed_{user_key}"] = False
        elif not symbol:
            st.error("No symbol selected.")
            st.session_state[f"armed_{user_key}"] = False
        elif symbol not in buy.markets or symbol not in sell.markets:
            st.error(f"Pair '{symbol}' not available on both exchanges.")
            st.session_state[f"armed_{user_key}"] = False
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

                if net_diff <= 0:
                    st.warning("Loss detected — stopped automatically.")
                    st.session_state[f"armed_{user_key}"] = False
                elif net_diff >= threshold:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if sim:
                        st.success(f"SIM PROFIT: +${profit:.2f} ({net_diff:.2f}%)")
                        st.session_state[f"log_{user_key}"].append(f"{timestamp}: Simulated +${profit:.2f}")
                    else:
                        st.success(f"REAL PROFIT: +${profit:.2f} ({net_diff:.2f}%)")
                        st.session_state[f"log_{user_key}"].append(f"{timestamp}: Real +${profit:.2f}")
                    st.session_state[f"armed_{user_key}"] = False
                else:
                    st.info(f"Monitoring... Diff: {net_diff:.2f}% (< {threshold}%)")

        if st.session_state[f"armed_{user_key}"]:
            time.sleep(5)
            st.rerun()

    # ------------------------------------------
    # TRADE HISTORY
    # ------------------------------------------
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.subheader("Recent Trades History")
    if st.session_state[f"log_{user_key}"]:
        st.write("\n".join(st.session_state[f"log_{user_key}"][-20:]))
    else:
        st.info("No trades yet. Click ▶️ Perform to start monitoring.")
    st.markdown('</div>', unsafe_allow_html=True)

elif authentication_status == False:
    st.error('Username/password is incorrect')
elif authentication_status == None:
    st.warning('Please enter your username and password')
