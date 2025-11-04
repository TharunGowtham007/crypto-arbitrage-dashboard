# app.py
import ccxt
import time
import logging
from decimal import Decimal, ROUND_DOWN
import streamlit as st

# ---------------- CONFIG ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Expand/adjust these lists as needed
EXCHANGES_LIST = ['binance', 'kucoin', 'kraken', 'coinbase', 'okx', 'gate', 'bitfinex', 'huobi', 'bybit', 'bitstamp']
CRYPTO_BASES = ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'XRP', 'LTC', 'DOT', 'LINK', 'AVAX', 'DOGE']
QUOTE_CURRENCIES = ['USDT', 'USD', 'INR', 'EUR', 'BUSD', 'USDC']
INVESTMENT_OPTIONS = [100, 250, 500, 1000, 5000, 10000]

DEFAULT_SLIPPAGE = 0.005  # 0.5%
DEFAULT_POLL = 5  # seconds

# ---------------- PAGE SETUP & STYLES ----------------
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide", page_icon="🔱")

st.markdown(r"""
<style>
:root { --trishul-size: 900px; }
html::before {
  content: "🔱";
  position: fixed;
  left: 50%;
  top: 42%;
  transform: translate(-50%, -50%);
  font-size: var(--trishul-size);
  color: #ffd580;
  opacity: 0.035;
  z-index: 0;
  pointer-events: none;
  filter: drop-shadow(0 6px 30px rgba(0,0,0,0.45));
}
.stApp {
  position: relative; z-index: 2;
  background: linear-gradient(135deg,#071224,#0f3b5c);
  padding: 22px; border-radius: 14px; color: #e7f6ff;
  box-shadow: 0 8px 40px rgba(2,20,40,0.6);
}
h1,h2,h3 { color: #8BE7FF; text-shadow: 0 2px 8px rgba(0,0,0,0.6); }
.stButton>button { background: linear-gradient(90deg,#00b09b,#96c93d); color:#012; font-weight:700; border-radius:8px; padding:8px 16px; }
.status-card { background: linear-gradient(145deg,#0b2230,#133a4d); padding:12px; border-radius:12px; margin-bottom:10px; color:#eaf9ff; }
.metric { background: linear-gradient(90deg,#022b3a,#0b4560); padding:12px; border-radius:10px; color:#eaf9ff; }
.error { background: linear-gradient(90deg,#7f0000,#ff3b3b); padding:10px; border-radius:8px; color:white; }
.success { background: linear-gradient(90deg,#007f3f,#00ff9d); padding:10px; border-radius:8px; color:black; }
.small-muted { color: #9fb3c8; font-size:12px; }
@media (max-width: 1200px) { :root{--trishul-size:520px;} }
@media (max-width: 800px) { :root{--trishul-size:380px;} }
</style>
""", unsafe_allow_html=True)

# ---------------- SESSION STATE ----------------
if 'auto_armed' not in st.session_state:
    st.session_state.auto_armed = False
if 'stop_requested' not in st.session_state:
    st.session_state.stop_requested = False
if 'log' not in st.session_state:
    st.session_state.log = []
if 'last_summary' not in st.session_state:
    st.session_state.last_summary = None

# ---------------- HELPERS ----------------
def safe_create_exchange(name, api_key=None, secret=None):
    """Return (exchange_instance, error_string_or_None)."""
    try:
        kwargs = {'enableRateLimit': True}
        if api_key:
            kwargs['apiKey'] = api_key
        if secret:
            kwargs['secret'] = secret
        inst = ccxt.__dict__[name](**kwargs)
        # non-blocking load markets attempt (some exchanges may rate-limit heavily)
        try:
            inst.load_markets()
        except Exception:
            pass
        return inst, None
    except Exception as e:
        logging.exception("create exchange fail")
        return None, str(e)

def fetch_price(exchange, symbol):
    """Return float price or None."""
    try:
        # ensure markets loaded
        if not getattr(exchange, 'markets', None):
            exchange.load_markets()
        if symbol not in exchange.markets:
            return None
        ticker = exchange.fetch_ticker(symbol)
        price = ticker.get('last') or ticker.get('close')
        return float(price) if price is not None else None
    except Exception as e:
        logging.debug(f"fetch_price error {exchange.id} {symbol}: {e}")
        return None

def get_taker_fee(exchange, symbol):
    """Best-effort taker fee decimal (e.g., 0.001)."""
    try:
        m = exchange.markets.get(symbol)
        if m:
            fee = m.get('taker') or m.get('takerFee')
            if fee:
                return float(fee)
    except Exception:
        pass
    try:
        return float(exchange.fees.get('trading', {}).get('taker', 0.001))
    except Exception:
        return 0.001

def get_withdraw_fee_base(exchange, base):
    """Estimate withdraw fee (in base coin) — fallback small default."""
    try:
        fees = getattr(exchange, 'fees', {})
        fee = fees.get('funding', {}).get('withdraw', {}).get(base)
        if fee:
            return float(fee)
    except Exception:
        pass
    return 0.0005

def round_amount(exchange, symbol, amt):
    """Round amount according to exchange precision if available."""
    try:
        m = exchange.markets.get(symbol)
        if not m:
            return amt
        prec = m.get('precision', {}).get('amount')
        if prec is None:
            return amt
        q = Decimal(amt).quantize(Decimal(10) ** -prec, rounding=ROUND_DOWN)
        return float(q)
    except Exception:
        return amt

def compute_arbitrage_metrics(price_buy, price_sell, taker_buy, taker_sell, withdraw_fee_base, slippage):
    """Return dict for per-1-base-unit metrics and net after slippage."""
    buy_fee_quote = price_buy * taker_buy
    withdraw_fee_quote = withdraw_fee_base * price_buy
    buy_cost = price_buy + buy_fee_quote + withdraw_fee_quote
    sell_revenue = price_sell * (1 - taker_sell)
    gross_profit = sell_revenue - price_buy
    net_profit = sell_revenue - buy_cost
    slippage_cost = abs(gross_profit) * slippage
    net_after_slippage = net_profit - slippage_cost
    return {
        'buy_cost': buy_cost,
        'sell_revenue': sell_revenue,
        'gross_profit': gross_profit,
        'net_profit': net_profit,
        'slippage_cost': slippage_cost,
        'net_after_slippage': net_after_slippage
    }

# ---------------- UI INPUTS ----------------
st.header("Arbitrage Dashboard")
top1, top2 = st.columns([2,1])
with top1:
    col1, col2 = st.columns(2)
    with col1:
        buy_ex = st.selectbox("Buy Exchange", EXCHANGES_LIST, index=0)
        buy_api = st.text_input(f"{buy_ex.upper()} API Key", type="password", key=f"{buy_ex}_api")
        buy_secret = st.text_input(f"{buy_ex.upper()} Secret", type="password", key=f"{buy_ex}_sec")
    with col2:
        sell_ex = st.selectbox("Sell Exchange", EXCHANGES_LIST, index=1)
        sell_api = st.text_input(f"{sell_ex.upper()} API Key", type="password", key=f"{sell_ex}_api")
        sell_secret = st.text_input(f"{sell_ex.upper()} Secret", type="password", key=f"{sell_ex}_sec")

with top2:
    base = st.selectbox("Base Asset", CRYPTO_BASES, index=0)
    quote = st.selectbox("Quote Currency", QUOTE_CURRENCIES, index=0)
    symbol = f"{base}/{quote}"

row3, row4 = st.columns(2)
with row3:
    investment_usd = st.selectbox("Investment (USD equivalent)", INVESTMENT_OPTIONS, index=2)
with row4:
    profit_threshold_pct = st.slider("Minimum profit threshold (%)", 0.1, 10.0, 1.0, step=0.1)

sim_mode = st.checkbox("Simulation Mode (recommended for testing)", value=True)
poll_interval = st.number_input("Poll interval (s)", min_value=2, max_value=60, value=DEFAULT_POLL)

st.markdown("---")

# ACTIONS
col_act1, col_act2 = st.columns(2)
with col_act1:
    perform_btn = st.button("▶️ Perform (arm bot)")
with col_act2:
    stop_btn = st.button("⛔ Stop Performing")

# placeholders
price_box = st.empty()
metrics_box = st.empty()
status_box = st.empty()
log_box = st.empty()

# ---------------- CORE EVALUATION ----------------
def evaluate_opportunity(buy_inst, sell_inst, symbol, investment_usd, slippage):
    # fetch prices
    price_buy = fetch_price(buy_inst, symbol)
    price_sell = fetch_price(sell_inst, symbol)
    if price_buy is None or price_sell is None:
        return None, "Price not available on one or both exchanges for symbol " + symbol
    # fees
    taker_buy = get_taker_fee(buy_inst, symbol) or 0.001
    taker_sell = get_taker_fee(sell_inst, symbol) or 0.001
    withdraw_base = get_withdraw_fee_base(buy_inst, base)
    # per-1-unit metrics
    arb = compute_arbitrage_metrics(price_buy, price_sell, taker_buy, taker_sell, withdraw_base, slippage)
    # compute base amount from investment USD
    base_amount = investment_usd / price_buy if price_buy > 0 else 0
    base_amount_rounded = round_amount(buy_inst, symbol, base_amount)
    if base_amount_rounded <= 0:
        return None, "Calculated trade amount is zero after rounding (increase investment)."
    scaled_net = arb['net_after_slippage'] * base_amount_rounded
    scaled_profit_pct = (scaled_net / (price_buy * base_amount_rounded)) * 100 if (price_buy * base_amount_rounded) > 0 else 0
    summary = {
        'price_buy': price_buy,
        'price_sell': price_sell,
        'taker_buy': taker_buy,
        'taker_sell': taker_sell,
        'withdraw_base': withdraw_base,
        'arb': arb,
        'base_amount': base_amount,
        'base_amount_rounded': base_amount_rounded,
        'scaled_net': scaled_net,
        'scaled_profit_pct': scaled_profit_pct
    }
    return summary, None

def render_summary(summary):
    if not summary:
        return
    price_buy = summary['price_buy']
    price_sell = summary['price_sell']
    tb = f"""
    <div class='status-card'>
    <h3>📊 Prices & Fees — {symbol}</h3>
    <b>Buy on:</b> {buy_ex.upper()} @ ${price_buy:.2f} &nbsp;&nbsp; <b>Sell on:</b> {sell_ex.upper()} @ ${price_sell:.2f}<br>
    <small class='small-muted'>Buy taker: {summary['taker_buy']*100:.3f}% • Sell taker: {summary['taker_sell']*100:.3f}% • Withdraw (base): {summary['withdraw_base']}</small>
    </div>
    """
    price_box.markdown(tb, unsafe_allow_html=True)

    arb = summary['arb']
    net_unit = arb['net_after_slippage']
    scaled_net = summary['scaled_net']
    pct = summary['scaled_profit_pct']
    metrics_md = f"""
    <div class='metric'>
    <h3>💰 Profit Estimate</h3>
    Net per 1 {base}: ${net_unit:.6f}<br>
    Investment: ${investment_usd} → ~{summary['base_amount_rounded']:.6f} {base}<br>
    <b>Estimated net profit:</b> ${scaled_net:.2f} ({pct:.3f}%)
    </div>
    """
    metrics_box.markdown(metrics_md, unsafe_allow_html=True)

    # verdict
    if scaled_net > 0 and pct >= profit_threshold_pct:
        status_box.markdown(f"<div class='success'>✅ Opportunity: Estimated net ${scaled_net:.2f} ({pct:.3f}%) — meets threshold {profit_threshold_pct}%</div>", unsafe_allow_html=True)
    elif scaled_net > 0:
        status_box.markdown(f"<div class='status-card'>⚠️ Positive but below threshold: ${scaled_net:.2f} ({pct:.3f}%)</div>", unsafe_allow_html=True)
    else:
        status_box.markdown(f"<div class='error'>❌ Not profitable: Estimated net ${scaled_net:.2f} ({pct:.3f}%).</div>", unsafe_allow_html=True)

# ---------------- PERFORM / STOP BEHAVIOR ----------------
# initialize exchange instances for read-only or authenticated use
buy_inst, buy_err = safe_create_exchange(buy_ex, buy_api or None, buy_secret or None)
sell_inst, sell_err = safe_create_exchange(sell_ex, sell_api or None, sell_secret or None)
if buy_err:
    st.error(f"Failed to initialize buy exchange {buy_ex}: {buy_err}")
    st.stop()
if sell_err:
    st.error(f"Failed to initialize sell exchange {sell_ex}: {sell_err}")
    st.stop()

# When user presses Perform (arm auto)
if perform_btn:
    # require keys to allow real execution; simulation allowed without keys
    if sim_mode:
        st.info("Armed auto-perform in Simulation Mode (no real orders will be placed).")
        st.session_state.auto_armed = True
        st.session_state.stop_requested = False
    else:
        if not (buy_api and buy_secret and sell_api and sell_secret):
            st.error("API keys & secrets required for both exchanges to run real trades. Provide them or use Simulation Mode.")
        else:
            st.session_state.auto_armed = True
            st.session_state.stop_requested = False
            st.success("🟢 Auto-perform ARMED (real mode). Bot will monitor and execute when opportunity meets criteria.")

# When user presses Stop
if stop_btn:
    st.session_state.auto_armed = False
    st.session_state.stop_requested = True
    st.warning("⛔ Auto-perform stopped by user.")

# ---------------- AUTO-MONITOR LOOP (runs inside session) ----------------
if st.session_state.auto_armed and not st.session_state.stop_requested:
    # single-iteration guard: evaluate, then either execute or rerun after sleep
    status_box.info("🔁 Auto-monitor armed — checking for opportunities...")
    # evaluate
    summary, err = evaluate_opportunity(buy_inst, sell_inst, symbol, investment_usd, DEFAULT_SLIPPAGE)
    if err:
        status_box.error(err)
        # wait and rerun
        time.sleep(poll_interval)
        st.experimental_rerun()
    else:
        render_summary(summary)
        st.session_state.last_summary = summary
        st.session_state.log.append(f"Checked {symbol} buy:{buy_ex} sell:{sell_ex} net:${summary['scaled_net']:.2f}")
        log_box.text("\n".join(st.session_state.log[-12:]))

        # decision: if profitable and meets threshold, execute (auto)
        scaled_net = summary['scaled_net']
        pct = summary['scaled_profit_pct']
        if scaled_net > 0 and pct >= profit_threshold_pct:
            # final authenticated instances (fresh) if real mode
            if sim_mode:
                # simulate execution: show popup-like message and log
                st.success(f"🔔 PROFIT DETECTED (SIM) — ${scaled_net:.2f} ({pct:.3f}%). Simulating execution now.")
                st.session_state.log.append(f"Simulated execution {symbol} net ${scaled_net:.2f}")
                # stop after simulated execution
                st.session_state.auto_armed = False
                st.experimental_rerun()
            else:
                # create authenticated exchange instances for execution
                buy_exec, berr = safe_create_exchange(buy_ex, buy_api, buy_secret)
                sell_exec, serr = safe_create_exchange(sell_ex, sell_api, sell_secret)
                if berr or serr or not buy_exec or not sell_exec:
                    status_box.error(f"Auth init failed before execution. buy_err={berr}, sell_err={serr}")
                    st.session_state.auto_armed = False
                    st.experimental_rerun()
                # re-evaluate fresh right before placing orders
                final_summary, ferr = evaluate_opportunity(buy_exec, sell_exec, symbol, investment_usd, DEFAULT_SLIPPAGE)
                if ferr or not final_summary:
                    status_box.error("Final re-check failed; aborting execution and continuing monitoring.")
                    time.sleep(poll_interval)
                    st.experimental_rerun()
                final_scaled = final_summary['scaled_net']
                final_pct = final_summary['scaled_profit_pct']
                if final_scaled <= 0 or final_pct < profit_threshold_pct:
                    status_box.warning("Final re-check shows not profitable. Aborting execution and continuing monitoring.")
                    time.sleep(poll_interval)
                    st.experimental_rerun()
                # compute trade amount and round by precision
                amt_base = final_summary['base_amount_rounded']
                amt_buy = round_amount(buy_exec, symbol, amt_base)
                amt_sell = round_amount(sell_exec, symbol, amt_base)
                trade_amt = min(amt_buy, amt_sell)
                if trade_amt <= 0:
                    status_box.error("Trade amount invalid after rounding. Aborting execution.")
                    st.session_state.auto_armed = False
                    st.experimental_rerun()
                # place orders: BUY then SELL (market)
                try:
                    status_box.info(f"Placing BUY order for {trade_amt:.8f} {base} on {buy_ex.upper()} ...")
                    buy_order = buy_exec.create_market_order(symbol, 'buy', trade_amt)
                    status_box.write("Buy response:", buy_order)
                except Exception as e:
                    status_box.error(f"BUY order failed: {e}")
                    st.session_state.auto_armed = False
                    st.experimental_rerun()
                try:
                    status_box.info(f"Placing SELL order for {trade_amt:.8f} {base} on {sell_ex.upper()} ...")
                    sell_order = sell_exec.create_market_order(symbol, 'sell', trade_amt)
                    status_box.write("Sell response:", sell_order)
                except Exception as e:
                    status_box.error(f"SELL order failed: {e}")
                    # note: if sell fails after buy succeeded, funds may be held — user must handle
                    st.session_state.auto_armed = False
                    st.experimental_rerun()
                # success
                st.success(f"✅ Auto-executed arbitrage: traded {trade_amt:.8f} {base}. Net est ${final_scaled:.2f} ({final_pct:.3f}%).")
                st.session_state.log.append(f"Executed {trade_amt:.8f} {base} buy:{buy_ex} sell:{sell_ex} net:${final_scaled:.2f}")
                st.session_state.auto_armed = False
                st.experimental_rerun()
        else:
            # not profitable — wait and rerun
            time.sleep(poll_interval)
            # if user pressed stop in another UI, stop
            if st.session_state.stop_requested:
                st.session_state.auto_armed = False
                st.session_state.stop_requested = False
                st.warning("⛔ Auto-perform stopped.")
                st.experimental_rerun()
            st.experimental_rerun()

# ---------------- UI: show last summary and logs if not auto-armed ----------------
if not st.session_state.auto_armed:
    # show last known summary (if exists)
    if st.session_state.last_summary:
        render_summary(st.session_state.last_summary)
    else:
        price_box.info("No checks run yet. Click 'Perform' to arm the bot (Simulation Mode recommended).")
    log_box.text("\n".join(st.session_state.log[-12:]))

# final safety note
st.markdown("---")
st.markdown("**Safety notes:** The bot re-checks prices immediately prior to execution. Market prices change quickly — even with checks there is execution risk. Always test in Simulation Mode and use small amounts first.")

# end of app
