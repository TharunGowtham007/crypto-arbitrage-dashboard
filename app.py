import ccxt
import streamlit as st
import asyncio
import logging
import datetime
import time

# -----------------------------
# Basic Config
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")
EXCHANGES = ccxt.exchanges

# -----------------------------
# Country -> Exchanges mapping
# -----------------------------
COUNTRIES = [
    'USA','Canada','UK','Germany','France','Italy','Spain','Netherlands','Sweden',
    'Norway','Denmark','Finland','Russia','China','Japan','South Korea','India','Singapore',
    'Australia','New Zealand','Brazil','Mexico','South Africa','UAE','Saudi Arabia','Turkey','Global'
]
COUNTRY_REGIONS = {country: EXCHANGES for country in COUNTRIES}

# -----------------------------
# CSS Styling
# -----------------------------
st.markdown("""
<style>
body, div[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #2C3E50 0%, #34495E 25%, #7F8CBD 50%, #BDC3C7 75%, #ECF0F1 100%);
    color: #1A1A1A;
    font-family: "Segoe UI", Roboto, Arial, sans-serif;
}

.block {
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 18px;
    backdrop-filter: blur(10px) saturate(120%);
    box-shadow: 0 6px 24px rgba(0,0,0,0.12);
    transition: transform 0.22s, box-shadow 0.22s;
}
.block:hover { transform: translateY(-3px); box-shadow: 0 14px 40px rgba(0,0,0,0.15); }

h1 { text-align:center; margin-bottom:16px; color:#1A1A1A; }
h4 { margin-top:10px; margin-bottom:6px; }

.stButton>button {
    background: linear-gradient(180deg, rgba(180,180,180,0.24), rgba(220,220,220,0.16));
    color: #1A1A1A;
    border: 1px solid rgba(200,200,200,0.3);
    border-radius: 14px;
    padding: 14px 22px;
    font-weight:600;
    font-size:16px;
    transition: transform 0.16s, box-shadow 0.16s;
    backdrop-filter: blur(6px);
}
.stButton>button:hover {
    transform: translateY(-2px) scale(1.04);
    box-shadow: 0 10px 28px rgba(0,0,0,0.12);
}
.stButton>button:active { transform: scale(0.97); }

input, textarea, select {
    background: rgba(255,255,255,0.12) !important;
    color: #1A1A1A !important;
    border: 1px solid rgba(255,255,255,0.25) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(5px) !important;
}

.live-card {
    background: rgba(255,255,255,0.12);
    border-radius:12px;
    padding:16px;
    margin-bottom:12px;
    backdrop-filter: blur(6px);
    transition: all 0.3s ease;
    color:#1A1A1A;
    font-weight:600;
    text-align:center;
}
.live-card:hover {
    transform: translateY(-2px) scale(1.01);
    box-shadow:0 8px 28px rgba(0,0,0,0.12);
}

input[type=checkbox] {
    accent-color: #7F8CBD;
    width: 18px;
    height: 18px;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Session State Defaults
# -----------------------------
defaults = {
    "armed": False, "stop": False, "log": [], "pair_list": [],
    "profitable_pairs": [], "selected_profitable": None,
    "live_monitor": "", "custom_pair": "BTC/USDT", "sim_mode": True,
    "buy_ex": EXCHANGES[0], "sell_ex": EXCHANGES[1],
    "buy_key":"", "buy_secret":"", "sell_key":"", "sell_secret":"",
    "profit_threshold": 1.0, "investment":1000.0
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# -----------------------------
# Exchange Helpers
# -----------------------------
def create_exchange(name, api_key=None, secret=None):
    try:
        cfg = {"enableRateLimit": True}
        if api_key and secret: cfg.update({"apiKey": api_key, "secret": secret})
        ex = getattr(ccxt, name)(cfg)
        ex.load_markets()
        return ex
    except: return None

def get_price(ex, sym):
    try: return ex.fetch_ticker(sym).get("last")
    except: return None

def get_fee(ex, sym, side):
    try:
        m = ex.market(sym)
        return m.get("taker",0.001) if side=="sell" else m.get("maker",0.001)
    except: return 0.001

# -----------------------------
# Header & Configuration
# -----------------------------
st.markdown("<h1>Arbitrage Dashboard</h1>", unsafe_allow_html=True)
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Configuration")
country = st.selectbox("Country/Region", COUNTRIES)

# Async find profitable pairs
async def find_profitable_pairs():
    st.session_state.profitable_pairs = []
    exchanges = COUNTRY_REGIONS.get(country, EXCHANGES)
    tasks = []
    for ex_name in exchanges:
        ex = create_exchange(ex_name)
        if not ex: continue
        for pair in ex.symbols[:50]:  # limit for speed
            for sell_name in exchanges:
                if sell_name==ex_name: continue
                sell_ex = create_exchange(sell_name)
                if not sell_ex or pair not in sell_ex.markets: continue
                pb = get_price(ex, pair)
                ps = get_price(sell_ex, pair)
                buy_fee = get_fee(ex, pair, "buy")
                sell_fee = get_fee(sell_ex, pair, "sell")
                if pb and ps and pb>0:
                    diff = ((ps-pb)/pb)*100 - (buy_fee+sell_fee)*100
                    if diff>0:
                        st.session_state.profitable_pairs.append({
                            "pair": pair,
                            "buy_ex": ex_name,
                            "sell_ex": sell_name,
                            "profit_percent": diff
                        })

if st.button("Find Profitable Pairs"):
    asyncio.run(find_profitable_pairs())
    if st.session_state.profitable_pairs:
        options = [f"{p['pair']} | Buy:{p['buy_ex']} | Sell:{p['sell_ex']} | Profit:{p['profit_percent']:.2f}%" for p in st.session_state.profitable_pairs[:20]]
        selected = st.selectbox("Select Profitable Pair", options)
        if selected:
            idx = options.index(selected)
            sel = st.session_state.profitable_pairs[idx]
            st.session_state.custom_pair = sel["pair"]
            st.session_state.buy_ex = sel["buy_ex"]
            st.session_state.sell_ex = sel["sell_ex"]

# -----------------------------
# Exchange Selection
# -----------------------------
col_ex1, col_ex2 = st.columns(2)
with col_ex1:
    buy_ex = st.selectbox("Buy Exchange", EXCHANGES, index=EXCHANGES.index(st.session_state.buy_ex))
with col_ex2:
    sell_ex = st.selectbox("Sell Exchange", EXCHANGES, index=EXCHANGES.index(st.session_state.sell_ex))

col_key1, col_key2 = st.columns(2)
with col_key1:
    buy_api_key = st.text_input(f"{buy_ex} API Key", type="password", key="buy_key")
    buy_secret = st.text_input(f"{buy_ex} Secret", type="password", key="buy_secret")
with col_key2:
    sell_api_key = st.text_input(f"{sell_ex} API Key", type="password", key="sell_key")
    sell_secret = st.text_input(f"{sell_ex} Secret", type="password", key="sell_secret")

# -----------------------------
# Load Available Pairs
# -----------------------------
def load_common_pairs(buy_ex, sell_ex):
    buy = create_exchange(buy_ex, st.session_state.buy_key, st.session_state.buy_secret)
    sell = create_exchange(sell_ex, st.session_state.sell_key, st.session_state.sell_secret)
    if not buy or not sell: return []
    return sorted(list(set(buy.symbols) & set(sell.symbols)))

if st.button("Load Available Pairs"):
    st.session_state.pair_list = load_common_pairs(buy_ex, sell_ex)
    if st.session_state.pair_list:
        st.success(f"{len(st.session_state.pair_list)} common pairs loaded.")
    else:
        st.warning("No common pairs found.")

# -----------------------------
# Crypto Pairs
# -----------------------------
st.markdown("<h4>Crypto Pairs</h4>", unsafe_allow_html=True)
if st.session_state.pair_list:
    pair_options = ["Type Custom Pair"] + st.session_state.pair_list
    pair_choice = st.selectbox("Select or Type Pair", pair_options, key="pair_choice")
    if pair_choice=="Type Custom Pair":
        symbol = st.text_input("Or Type Custom Pair", value=st.session_state.custom_pair)
    else:
        symbol = pair_choice
else:
    symbol = st.text_input("Or Type Custom Pair", value=st.session_state.custom_pair)
st.session_state.custom_pair = symbol

# -----------------------------
# Investment & Profit Threshold
# -----------------------------
col_inv, col_thr = st.columns(2)
with col_inv:
    st.session_state.investment = st.number_input("Investment ($)", min_value=1.0, value=st.session_state.investment)
with col_thr:
    st.session_state.profit_threshold = st.slider("Profit Threshold (%)", 0.1, 20.0, st.session_state.profit_threshold)

# -----------------------------
# Simulation Checkbox
# -----------------------------
# Only create the checkbox, let Streamlit handle the session state automatically
st.session_state.setdefault("sim_mode", True)
sim_mode = st.checkbox("Simulation", key="sim_mode")


# -----------------------------
# Perform / Stop Buttons
# -----------------------------
colA, colB = st.columns(2)
with colA: perform = st.button("Perform")
with colB: stop = st.button("Stop")
st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# Main Bot Logic
# -----------------------------
if perform:
    st.session_state.armed = True
    st.session_state.stop = False
    st.success("Bot armed — waiting for profitable signal...")

if stop:
    st.session_state.armed=False
    st.session_state.stop=True
    st.warning("Bot stopped")

if st.session_state.armed and not st.session_state.stop:
    buy = create_exchange(buy_ex, buy_api_key, buy_secret)
    sell = create_exchange(sell_ex, sell_api_key, sell_secret)
    if not buy or not sell or not symbol:
        st.error("Exchange init failed or symbol missing.")
        st.session_state.armed=False
    elif symbol not in buy.markets or symbol not in sell.markets:
        st.error(f"Pair '{symbol}' not available on both exchanges.")
        st.session_state.armed=False
    else:
        pb = get_price(buy, symbol)
        ps = get_price(sell, symbol)
        if not pb or not ps or pb<=0 or ps<=0:
            st.warning("Invalid prices fetched.")
            st.session_state.live_monitor="Invalid prices."
        else:
            buy_fee = get_fee(buy, symbol, "buy")
            sell_fee = get_fee(sell, symbol, "sell")
            diff = ((ps-pb)/pb)*100
            fee_cost = (buy_fee + sell_fee)*100
            net_diff = diff - fee_cost
            profit = st.session_state.investment*(net_diff/100)
            st.session_state.live_monitor = f"Buy: ${pb:.2f} | Sell: ${ps:.2f} | Diff: {net_diff:.2f}% | Profit: ${profit:.2f}"

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if net_diff <=0:
                st.warning("Loss detected — bot stopped.")
                st.session_state.armed=False
            elif net_diff>=st.session_state.profit_threshold:
                if st.session_state.sim_mode:
                    st.success(f"SIM PROFIT: +${profit:.2f} ({net_diff:.2f}%)")
                    st.session_state.log.append(f"{timestamp}: Simulated +${profit:.2f}")
                else:
                    st.success(f"REAL PROFIT: +${profit:.2f} ({net_diff:.2f}%)")
                    st.session_state.log.append(f"{timestamp}: Real +${profit:.2f}")
                st.session_state.armed=False

    if st.session_state.armed:
        time.sleep(1)
        st.experimental_rerun()

# -----------------------------
# Live Monitoring
# -----------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Live Monitoring")
if st.session_state.live_monitor:
    st.markdown(f'<div class="live-card">{st.session_state.live_monitor}</div>', unsafe_allow_html=True)
else:
    st.info("No active monitoring.")
st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# Recent Trades
# -----------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Recent Trades History")
if st.session_state.log:
    st.write("\n".join(st.session_state.log[-20:]))
else:
    st.info("No trades yet.")
st.markdown('</div>', unsafe_allow_html=True)
