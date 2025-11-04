# app.py
import ccxt
import streamlit as st
import time
import logging
import datetime
from decimal import Decimal, ROUND_DOWN
import pandas as pd

# ---------------------- CONFIG ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")

EXCHANGES = ["binance", "kucoin", "kraken", "coinbase", "okx", "bitfinex", "bybit", "gate"]
COMMON_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT", "DOT/USDT", "DOGE/USDT", "Custom"]
DEFAULT_POLL = 4  # seconds
MAX_HISTORY = 50

# ---------------------- STYLE (DARK + GOLD TRISHUL) ----------------------
st.markdown(
    """
<style>
:root { --gold: #b8860b; --muted: #9aa3a8; --panel: #0b0f12; --card: #0f1416; --accent: #0ad1c8; }
html, body, [class*="css"]  {
    background: #030405!important;
    color: #cbd5d1!important;
    font-family: Inter, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

/* Trishul background (faint gold, centered) */
div[data-testid="stAppViewContainer"] {
    background-color: #030405;
    position: relative;
}
div[data-testid="stAppViewContainer"]::before{
    content: "";
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%,-50%);
    width: 680px;
    height: 680px;
    background-image: url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg');
    background-repeat: no-repeat;
    background-position: center;
    background-size: contain;
    opacity: 0.06;
    filter: drop-shadow(0 6px 30px rgba(184,134,11,0.16));
    z-index: 0;
    pointer-events: none;
}

/* Page title */
h1 {
    color: var(--gold) !important;
    text-align: left;
    font-weight: 700;
    margin-bottom: 6px;
}

/* panels / cards */
.block {
    background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
    border: 1px solid rgba(184,134,11,0.06);
    border-radius: 12px;
    padding: 14px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.6);
    z-index: 1;
}

/* metrics */
.metric {
    padding: 10px;
    border-radius: 10px;
    color: #e6efe9;
}
.metric-buy { background: linear-gradient(90deg, rgba(0,128,96,0.06), rgba(0,128,96,0.03)); border-left: 4px solid #00b894; }
.metric-sell{ background: linear-gradient(90deg, rgba(220,38,38,0.06), rgba(220,38,38,0.03)); border-left: 4px solid #ff6b6b; }
.metric-profit{ background: linear-gradient(90deg, rgba(184,134,11,0.06), rgba(184,134,11,0.03)); border-left: 4px solid var(--gold); }

/* small muted text */
.small { color: #9aa3a8; font-size:13px; }

/* buttons */
.stButton>button {
    background: linear-gradient(90deg, #c59b1a, #b8860b) !important;
    color: #041014 !important;
    border-radius: 8px !important;
    padding: 10px 16px !important;
    font-weight: 700;
}
.stButton>button:hover { transform: translateY(-2px); }

/* inputs */
.stTextInput input, .stNumberInput input, .stSelectbox {
    background: rgba(255,255,255,0.02) !important;
    color: #dbe9e2 !important;
    border-radius: 6px !important;
    border: 1px solid rgba(184,134,11,0.06) !important;
}

/* chart container */
.chart-card {
    background: rgba(255,255,255,0.01);
    border-radius: 10px;
    padding: 8px;
    border: 1px solid rgba(184,134,11,0.04);
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------- SESSION STATE ----------------------
if "armed" not in st.session_state:
    st.session_state.armed = False
if "stop_requested" not in st.session_state:
    st.session_state.stop_requested = False
if "log" not in st.session_state:
    st.session_state.log = []
if "history" not in st.session_state:
    st.session_state.history = {"ts": [], "buy": [], "sell": [], "net_pct": []}

# ---------------------- HELPERS ----------------------
def safe_init_exchange(name: str, api_key: str = None, secret: str = None):
    try:
        params = {"enableRateLimit": True}
        if api_key and secret:
            params.update({"apiKey": api_key, "secret": secret})
        ex = getattr(ccxt, name)(params)
        try:
            ex.load_markets()
        except Exception:
            # OK if markets can't be loaded right away
            pass
        return ex
    except Exception as e:
        logging.debug(f"init {name} failed: {e}")
        return None

def fetch_price(exchange, symbol):
    try:
        if exchange is None:
            return None
        # ensure markets
        if not getattr(exchange, "markets", None):
            try:
                exchange.load_markets()
            except Exception:
                pass
        # symbol valid?
        if symbol not in getattr(exchange, "markets", {}):
            return None
        ticker = exchange.fetch_ticker(symbol)
        val = ticker.get("last") or ticker.get("close")
        return float(val) if val is not None else None
    except Exception as e:
        logging.debug(f"fetch_price {getattr(exchange,'id',None)} {symbol} err: {e}")
        return None

def fetch_fee_pct(exchange, symbol):
    """
    Returns effective fee percent (taker preferred) as a float (e.g. 0.1 for 0.1%)
    Attempts: fetch_trading_fee -> markets info -> exchange.fees fallback
    """
    if exchange is None:
        return 0.1  # conservative fallback 0.1%
    try:
        # Many exchanges support fetch_trading_fee
        info = exchange.fetch_trading_fee(symbol)
        taker = info.get("taker")
        maker = info.get("maker")
        # pick taker if available (we are using market or quick exec)
        rate = taker if taker is not None else maker
        if rate is not None:
            return float(rate) * 100.0  # return in percent (0.1% -> 0.1)
    except Exception:
        pass
    try:
        # markets precision may have fee info
        m = getattr(exchange, "markets", {}).get(symbol, {})
        if m:
            taker = m.get("taker") or m.get("takerFee")
            if taker:
                return float(taker) * 100.0
    except Exception:
        pass
    try:
        # fallback to exchange.fees
        return float(getattr(exchange, "fees", {}).get("trading", {}).get("taker", 0.001)) * 100.0
    except Exception:
        return 0.1

def round_base_amount(exchange, symbol, amount):
    try:
        m = getattr(exchange, "markets", {}).get(symbol, {})
        precision = m.get("precision", {}).get("amount")
        if precision is None:
            return float(amount)
        q = Decimal(amount).quantize(Decimal(10) ** -precision, rounding=ROUND_DOWN)
        return float(q)
    except Exception:
        return float(amount)

def execute_market_orders(buy_ex, sell_ex, symbol, amount):
    """
    Attempt to create market orders. This is simplistic and assumes
    both exchanges support create_market_order; in many real cases you'd need
    exchange-specific flow, order books, balances, etc.
    """
    try:
        # use create_market_order where available (ccxt naming varies)
        buy_resp = buy_ex.create_market_buy_order(symbol, amount) if hasattr(buy_ex, "create_market_buy_order") else buy_ex.create_order(symbol, 'market', 'buy', amount)
    except Exception as e:
        buy_resp = {"error": str(e)}
    try:
        sell_resp = sell_ex.create_market_sell_order(symbol, amount) if hasattr(sell_ex, "create_market_sell_order") else sell_ex.create_order(symbol, 'market', 'sell', amount)
    except Exception as e:
        sell_resp = {"error": str(e)}
    return buy_resp, sell_resp

# ---------------------- UI ----------------------
st.title("Arbitrage Dashboard")
st.markdown('<div class="small">Dark theme · live prices & fees · auto-stop on loss</div>', unsafe_allow_html=True)
st.markdown("")

# top config panel
with st.container():
    st.markdown('<div class="block">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2,2,1])
    with c1:
        buy_exchange = st.selectbox("Buy exchange", EXCHANGES, index=0)
        buy_api = st.text_input(f"{buy_exchange} API key (optional)", type="password", key="buy_api")
        buy_secret = st.text_input(f"{buy_exchange} Secret (optional)", type="password", key="buy_secret")
    with c2:
        sell_exchange = st.selectbox("Sell exchange", EXCHANGES, index=1)
        sell_api = st.text_input(f"{sell_exchange} API key (optional)", type="password", key="sell_api")
        sell_secret = st.text_input(f"{sell_exchange} Secret (optional)", type="password", key="sell_secret")
    with c3:
        pair_choice = st.selectbox("Pair", COMMON_PAIRS, index=0)
        if pair_choice == "Custom":
            symbol = st.text_input("Enter pair (e.g. BTC/USDT)", value="BTC/USDT")
        else:
            symbol = pair_choice
    st.markdown("---")
    d1, d2, d3 = st.columns([1,1,1])
    with d1:
        investment = st.number_input("Investment (USD)", min_value=1.0, value=1000.0, step=1.0)
    with d2:
        profit_threshold = st.slider("Minimum net profit (%)", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
    with d3:
        sim_mode = st.checkbox("Simulation mode (no real orders)", value=True)
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    p1, p2 = st.columns([1,1])
    with p1:
        perform = st.button("Perform")
    with p2:
        stop_btn = st.button("Stop")
    st.markdown('</div>', unsafe_allow_html=True)

# placeholders
price_col = st.container()
status_col = st.empty()
history_col = st.container()

# ---------------------- Button behavior ----------------------
if perform:
    st.session_state.armed = True
    st.session_state.stop_requested = False
    st.success("Bot armed — monitoring live opportunities.")
if stop_btn:
    st.session_state.armed = False
    st.session_state.stop_requested = True
    st.warning("Monitoring stopped by user.")

# ---------------------- Monitoring loop (single iteration per run) ----------------------
if st.session_state.armed and not st.session_state.stop_requested:
    # init exchanges
    buy_ex = safe_init_exchange(buy_exchange, st.session_state.get("buy_api") or buy_api, st.session_state.get("buy_secret") or buy_secret)
    sell_ex = safe_init_exchange(sell_exchange, st.session_state.get("sell_api") or sell_api, st.session_state.get("sell_secret") or sell_secret)

    if not buy_ex or not sell_ex:
        status_col.error("Exchange init failed for one or both exchanges. Try different ones.")
        st.session_state.armed = False
    else:
        # fetch prices
        pb = fetch_price(buy_ex, symbol)
        ps = fetch_price(sell_ex, symbol)

        # show availability
        if pb is None or ps is None:
            status_col.warning("Price unavailable for pair on one or both exchanges. Monitoring paused.")
            st.session_state.armed = False
        else:
            # fetch fees (percent values)
            buy_fee_pct = fetch_fee_pct(buy_ex, symbol)   # e.g. 0.1 means 0.1%
            sell_fee_pct = fetch_fee_pct(sell_ex, symbol)
            total_fee_pct = buy_fee_pct + sell_fee_pct

            # compute spread and net pct after fees
            raw_pct = ((ps - pb) / pb) * 100.0
            net_pct = raw_pct - total_fee_pct  # net percent after subtracting both fees
            estimated_profit_usd = investment * (net_pct / 100.0)

            # update history
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            st.session_state.history["ts"].append(ts)
            st.session_state.history["buy"].append(pb)
            st.session_state.history["sell"].append(ps)
            st.session_state.history["net_pct"].append(net_pct)
            if len(st.session_state.history["ts"]) > MAX_HISTORY:
                for k in st.session_state.history:
                    st.session_state.history[k].pop(0)

            # display metrics
            with price_col:
                st.markdown('<div class="block">', unsafe_allow_html=True)
                cols = st.columns([1,1,1])
                with cols[0]:
                    st.markdown(f"<div class='metric metric-buy'><strong>Buy @ {buy_exchange.upper()}</strong><div style='font-size:18px;margin-top:6px;'>${pb:,.4f}</div><div class='small'>Fee: {buy_fee_pct:.4f}%</div></div>", unsafe_allow_html=True)
                with cols[1]:
                    st.markdown(f"<div class='metric metric-sell'><strong>Sell @ {sell_exchange.upper()}</strong><div style='font-size:18px;margin-top:6px;'>${ps:,.4f}</div><div class='small'>Fee: {sell_fee_pct:.4f}%</div></div>", unsafe_allow_html=True)
                with cols[2]:
                    st.markdown(f"<div class='metric metric-profit'><strong>Net (after fees)</strong><div style='font-size:18px;margin-top:6px;'>{net_pct:,.4f}%</div><div class='small'>Est profit: ${estimated_profit_usd:,.2f} on ${investment}</div></div>", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

            # chart / history
            with history_col:
                st.markdown('<div class="block chart-card">', unsafe_allow_html=True)
                try:
                    df = pd.DataFrame({
                        "Buy": st.session_state.history["buy"],
                        "Sell": st.session_state.history["sell"],
                        "Net %": st.session_state.history["net_pct"]
                    }, index=st.session_state.history["ts"])
                    st.line_chart(df[["Buy", "Sell"]])
                    st.markdown("</div>", unsafe_allow_html=True)
                except Exception:
                    st.markdown("</div>", unsafe_allow_html=True)

            # enforcement: immediate stop if net profit <= 0
            if net_pct <= 0:
                status_col.error(f"LOSS DETECTED — net% = {net_pct:.4f}%. Aborting any execution and stopping monitoring.")
                st.session_state.log.append(f"{datetime.datetime.now().isoformat()}: LOSS DETECTED: {net_pct:.4f}% on {symbol} ({buy_exchange}->{sell_exchange})")
                st.session_state.armed = False
            elif net_pct < profit_threshold:
                status_col.info(f"Net {net_pct:.4f}% is below threshold {profit_threshold}%. Continuing monitoring.")
                # continue monitoring: sleep + rerun
                time.sleep(DEFAULT_POLL)
                st.experimental_rerun()
            else:
                # net_pct >= threshold and > 0 => candidate
                status_col.success(f"PROFIT CANDIDATE: net {net_pct:.4f}% — estimated ${estimated_profit_usd:,.2f}")
                st.session_state.log.append(f"{datetime.datetime.now().isoformat()}: Candidate net {net_pct:.4f}% estimated ${estimated_profit_usd:,.2f}")

                if sim_mode:
                    status_col.info("Simulation mode ON — logging simulated execution and stopping monitor.")
                    st.session_state.log.append(f"{datetime.datetime.now().isoformat()}: SIMULATED EXECUTION: ${estimated_profit_usd:,.2f}")
                    st.session_state.armed = False
                else:
                    # compute base amount and rounding
                    base_symbol = symbol.split("/")[0]
                    approx_base_amount = investment / pb if pb > 0 else 0
                    base_amount = round_base_amount(buy_ex, symbol, approx_base_amount)
                    if base_amount <= 0:
                        status_col.error("Computed trade amount is zero after rounding. Aborting.")
                        st.session_state.armed = False
                    else:
                        status_col.info(f"Attempting market orders for {base_amount:.8f} {base_symbol} ...")
                        buy_resp, sell_resp = execute_market_orders(buy_ex, sell_ex, symbol, base_amount)
                        st.write("Buy response:", buy_resp)
                        st.write("Sell response:", sell_resp)
                        # rudimentary success check
                        if isinstance(buy_resp, dict) and "error" in buy_resp:
                            status_col.error(f"Buy failed: {buy_resp['error']}")
                            st.session_state.log.append(f"{datetime.datetime.now().isoformat()}: BUY FAILED: {buy_resp['error']}")
                            st.session_state.armed = False
                        elif isinstance(sell
