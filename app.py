# app.py
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

# Use the list of exchanges available in ccxt
EXCHANGES = ccxt.exchanges

# ------------------------------------------
# STYLE (Dark Theme + Faint Golden Trishul)
# ------------------------------------------
st.markdown(
    """
<style>
body {
    background-color: #121212;
    color: #e0e0e0;
    font-family: "Segoe UI", sans-serif;
}
div[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at center, rgba(255, 215, 0, 0.06), rgba(0, 0, 0, 0.95)),
                url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg');
    background-size: 25%;
    background-position: center;
    background-repeat: no-repeat;
    background-attachment: fixed;
}
h1 {
    color: #f1c40f;
    text-align: center;
    font-weight: 700;
    margin-bottom: 20px;
}
.block {
    background: rgba(255, 255, 255, 0.02);
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 2px 10px rgba(255, 215, 0, 0.03);
    margin-bottom: 25px;
}
.metric-green {
    background-color: rgba(40,167,69,0.08);
    padding: 15px;
    border-radius: 8px;
    border-left: 4px solid #28a745;
}
.metric-red {
    background-color: rgba(220,53,69,0.08);
    padding: 15px;
    border-radius: 8px;
    border-left: 4px solid #dc3545;
}
.metric-profit {
    background-color: rgba(255,193,7,0.06);
    padding: 15px;
    border-radius: 8px;
    border-left: 4px solid #ffc107;
}
.stButton>button {
    background-color: #f1c40f;
    color: black;
    border: none;
    border-radius: 5px;
    padding: 10px 22px;
    font-size: 16px;
    font-weight: 600;
}
.stButton>button:hover {
    background-color: #d4ac0d;
    color: #000;
}
</style>
""",
    unsafe_allow_html=True,
)

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
# INPUT UI
# ------------------------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Configuration")

col1, col2 = st.columns(2)
with col1:
    # Populate selectbox from ccxt.exchanges list for maximum options
    buy_ex = st.selectbox("Buy Exchange", EXCHANGES, index=0)
    buy_api_key = st.text_input(f"{buy_ex} API Key (optional)", type="password", key="buy_key")
    buy_secret = st.text_input(f"{buy_ex} Secret (optional)", type="password", key="buy_secret")
with col2:
    sell_ex = st.selectbox("Sell Exchange", EXCHANGES, index=1)
    sell_api_key = st.text_input(f"{sell_ex} API Key (optional)", type="password", key="sell_key")
    sell_secret = st.text_input(f"{sell_ex} Secret (optional)", type="password", key="sell_secret")

symbol = st.text_input("Crypto Pair (e.g., BTC/USDT, ETH/BTC)", value="BTC/USDT")
st.caption("Enter any available pair on the selected exchanges.")

investment = st.number_input("Investment ($)", min_value=1.0, value=1000.0, step=1.0)
threshold = st.slider("Profit Threshold (%)", 0.1, 10.0, 1.0)

colA, colB = st.columns(2)
with colA:
    perform = st.button("Perform")
with colB:
    stop = st.button("Stop")

sim = st.checkbox("Simulation Mode (no real orders)", True)
st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------
# EXCHANGE HELPERS
# ------------------------------------------
def create_exchange(name, api_key=None, secret=None):
    """Safely create ccxt exchange instance."""
    try:
        config = {"enableRateLimit": True}
        if api_key and secret:
            config.update({"apiKey": api_key, "secret": secret})
        ex = getattr(ccxt, name)(config)
        # load markets but ignore failures
        try:
            ex.load_markets()
        except Exception:
            pass
        return ex
    except Exception as e:
        logging.error(f"Failed to initialize {name}: {e}")
        return None


def get_price(ex, sym):
    """Fetch last/close price; return float or None."""
    try:
        if ex is None:
            return None
        # ensure markets loaded
        if not getattr(ex, "markets", None):
            try:
                ex.load_markets()
            except Exception:
                pass
        # check pair existence
        if sym not in getattr(ex, "markets", {}):
            return None
        t = ex.fetch_ticker(sym)
        val = t.get("last") or t.get("close")
        return float(val) if val is not None else None
    except Exception as e:
        logging.debug(f"Failed to fetch price for {sym} on {getattr(ex,'id', None)}: {e}")
        return None


def get_trading_fee(ex, symbol):
    """
    Return (maker, taker) as fractions (e.g., 0.001 for 0.1%).
    Falls back to safe defaults if not available.
    """
    try:
        if ex is None:
            return 0.001, 0.001
        try:
            info = ex.fetch_trading_fee(symbol)
            maker = info.get("maker", None)
            taker = info.get("taker", None)
            if maker is not None and taker is not None:
                return float(maker), float(taker)
        except Exception:
            # not all exchanges implement fetch_trading_fee
            pass
        # try markets metadata
        m = getattr(ex, "markets", {}).get(symbol, {})
        if m:
            maker = m.get("maker") or m.get("makerFee") or None
            taker = m.get("taker") or m.get("takerFee") or None
            if maker is not None and taker is not None:
                return float(maker), float(taker)
        # fallback to exchange.fees data
        try:
            taker = getattr(ex, "fees", {}).get("trading", {}).get("taker", 0.001)
            maker = getattr(ex, "fees", {}).get("trading", {}).get("maker", taker)
            return float(maker), float(taker)
        except Exception:
            return 0.001, 0.001
    except Exception:
        return 0.001, 0.001


def execute_trade(ex, side, symbol, amount, price):
    """Simple wrapper for limit order execution. Returns order or None."""
    try:
        order = ex.create_order(symbol, "limit", side, amount, price)
        return order
    except Exception as e:
        logging.error(f"Trade execution failed: {e}")
        return None


def round_base_amount(exchange, symbol, amount):
    """Round amount according to exchange market precision if available."""
    try:
        m = getattr(exchange, "markets", {}).get(symbol, {})
        precision = m.get("precision", {}).get("amount")
        if precision is None:
            return float(amount)
        q = Decimal(amount).quantize(Decimal(10) ** -precision, rounding=ROUND_DOWN)
        return float(q)
    except Exception:
        return float(amount)


# ------------------------------------------
# MAIN LOGIC
# ------------------------------------------
if perform:
    st.session_state.armed = True
    st.session_state.stop = False
    st.success("Bot armed — monitoring live prices and fees.")

if stop:
    st.session_state.armed = False
    st.session_state.stop = True
    st.warning("Monitoring stopped by user.")

if st.session_state.armed and not st.session_state.stop:
    # initialize exchanges (using provided keys where possible)
    buy = create_exchange(buy_ex, buy_api_key or None, buy_secret or None)
    sell = create_exchange(sell_ex, sell_api_key or None, sell_secret or None)

    if not buy or not sell:
        st.error("Exchange initialization failed for one or both exchanges. Check exchange names and API keys.")
        st.session_state.armed = False
    else:
        # fetch prices safely
        pb = get_price(buy, symbol)
        ps = get_price(sell, symbol)

        if (pb is None) or (ps is None):
            st.warning("Price unavailable for the pair on one or both exchanges. Monitoring paused.")
            st.session_state.armed = False
        else:
            # ensure numeric
            try:
                pb = float(pb)
                ps = float(ps)
            except Exception:
                st.error("Received non-numeric price data; aborting monitoring.")
                st.session_state.armed = False
                pb = None
                ps = None

            if pb is not None and ps is not None:
                # get fees (fractions)
                buy_maker, buy_taker = get_trading_fee(buy, symbol)
                sell_maker, sell_taker = get_trading_fee(sell, symbol)
                # use taker fees for aggressive execution estimation
                buy_fee = buy_taker
                sell_fee = sell_taker

                total_fee_fraction = buy_fee + sell_fee  # e.g. 0.001 + 0.001 = 0.002
                # estimated fees in USD relative to invested USD (approx)
                estimated_fee_usd = investment * total_fee_fraction

                # gross profit in USD (sell-buy) * (investment / buy_price)
                # approximate base amount purchased with investment
                approx_base_amount = investment / pb if pb > 0 else 0.0
                gross_profit_usd = (ps - pb) * approx_base_amount
                net_profit_usd = gross_profit_usd - estimated_fee_usd
                # percent on investment
                diff_percent = (net_profit_usd / investment) * 100.0 if investment > 0 else 0.0

                # display metrics
                colx, coly, colz = st.columns(3)
                with colx:
                    st.markdown(
                        f"<div class='metric-green'><strong>Buy @ {buy_ex.upper()}</strong><div style='font-size:18px;margin-top:6px;'>${pb:,.6f}</div><div style='color:#9aa3a8;font-size:12px;margin-top:6px;'>Est taker fee: {buy_fee*100:.4f}%</div></div>",
                        unsafe_allow_html=True,
                    )
                with coly:
                    st.markdown(
                        f"<div class='metric-red'><strong>Sell @ {sell_ex.upper()}</strong><div style='font-size:18px;margin-top:6px;'>${ps:,.6f}</div><div style='color:#9aa3a8;font-size:12px;margin-top:6px;'>Est taker fee: {sell_fee*100:.4f}%</div></div>",
                        unsafe_allow_html=True,
                    )
                with colz:
                    st.markdown(
                        f"<div class='metric-profit'><strong>Net Profit</strong><div style='font-size:18px;margin-top:6px;'>${net_profit_usd:,.2f} ({diff_percent:.4f}%)</div><div style='color:#9aa3a8;font-size:12px;margin-top:6px;'>Estimated fees: ${estimated_fee_usd:,.2f}</div></div>",
                        unsafe_allow_html=True,
                    )

                # enforce safety: immediate abort if net profit <= 0
                if net_profit_usd <= 0:
                    st.error(f"Loss detected after estimated fees (${net_profit_usd:.2f}). Aborting and stopping monitoring.")
                    st.session_state.log.append(f"{datetime.datetime.now().isoformat()}: Aborted — loss ${net_profit_usd:.2f}")
                    st.session_state.armed = False
                elif diff_percent < threshold:
                    st.info(f"Opportunity present but net% {diff_percent:.4f}% is below threshold {threshold}%. Continuing monitoring.")
                    # continue monitoring loop
                    time.sleep(3)
                    st.experimental_rerun()
                else:
                    # profitable by threshold after fees
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if sim:
                        st.success(f"Simulated trade: Estimated profit ${net_profit_usd:.2f} ({diff_percent:.4f}%) — logging and stopping.")
                        st.session_state.log.append(f"{timestamp}: SIMULATED trade +${net_profit_usd:.2f} ({diff_percent:.4f}%)")
                        st.session_state.armed = False
                    else:
                        # attempt real execution (simple limit orders at current prices)
                        approx_amount = round_base_amount(buy, symbol, approx_base_amount)
                        if approx_amount <= 0:
                            st.error("Calculated trade amount is zero after rounding. Aborting.")
                            st.session_state.armed = False
                        else:
                            st.info(f"Attempting execution for {approx_amount:.8f} units.")
                            buy_order = execute_trade(buy, "buy", symbol, approx_amount, pb)
                            sell_order = execute_trade(sell, "sell", symbol, approx_amount, ps)
                            # rudimentary check — real trading requires thorough order verification
                            if buy_order is None or sell_order is None:
                                st.error("One or both orders failed. Check API permissions, balances, and order responses.")
                                st.session_state.log.append(f"{timestamp}: REAL trade failed (buy/sell response issues).")
                            else:
                                st.success(f"Executed trades (check exchange order history). Estimated net profit: ${net_profit_usd:.2f}")
                                st.session_state.log.append(f"{timestamp}: REAL trade +${net_profit_usd:.2f} ({diff_percent:.4f}%)")
                            st.session_state.armed = False

    # small pause before next run if not stopped by above branches
    time.sleep(1)
    st.experimental_rerun()

# ------------------------------------------
# TRADE HISTORY
# ------------------------------------------
st.markdown('<div class="block">', unsafe_allow_html=True)
st.subheader("Recent Trades / Logs")
if st.session_state.log:
    st.write("\n".join(st.session_state.log[-30:]))
else:
    st.info("No trades yet. Click Perform to start monitoring.")
st.markdown('</div>', unsafe_allow_html=True)
