# app.py
import ccxt
import time
import logging
from decimal import Decimal, ROUND_DOWN
import streamlit as st

# ---------- CONFIG ----------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

EXCHANGES = ['binance', 'kucoin', 'kraken', 'coinbase', 'okx', 'gate', 'bitfinex', 'huobi', 'bybit', 'bitstamp']
BASE_ASSETS = ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'XRP', 'LTC', 'DOT', 'LINK', 'AVAX', 'DOGE']
QUOTES = ['USDT', 'USD', 'INR', 'EUR', 'BUSD', 'USDC']
INVESTMENTS = [100, 250, 500, 1000, 5000, 10000]

DEFAULT_SLIPPAGE = 0.005
DEFAULT_POLL = 5

# ---------- PAGE & SAFE CSS ----------
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide", page_icon="🔱")

# Safe CSS: trishul background behind UI; will not cover widgets
st.markdown(r"""
<style>
:root { --trishul-size: 700px; }
html::before {
  content: "";
  position: fixed;
  left: 50%;
  top: 42%;
  transform: translate(-50%, -50%);
  width: var(--trishul-size);
  height: var(--trishul-size);
  /* use a public SVG — fallback to subtle color if unavailable */
  background-image: url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg');
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  opacity: 0.06;
  z-index: -1;               /* VERY IMPORTANT: behind UI */
  pointer-events: none;
  filter: drop-shadow(0 8px 30px rgba(0,0,0,0.45));
}
.stApp { position: relative; z-index: 1; background: linear-gradient(135deg,#071224,#0f3b5c); padding: 20px; border-radius: 12px; color: #e7f6ff; }
h1,h2,h3 { color: #8BE7FF; text-shadow: 0 2px 8px rgba(0,0,0,0.5); }
.stButton>button { background: linear-gradient(90deg,#00b09b,#96c93d); color:#012; font-weight:700; border-radius:8px; padding:8px 14px; }
.status-card { background: linear-gradient(145deg,#0b2230,#133a4d); padding:12px; border-radius:10px; color:#eaf9ff; }
.metric { background: linear-gradient(90deg,#022b3a,#0b4560); padding:12px; border-radius:10px; color:#eaf9ff; }
.success { background: linear-gradient(90deg,#007f3f,#00ff9d); padding:10px; border-radius:8px; color:black; }
.error { background: linear-gradient(90deg,#7f0000,#ff3b3b); padding:10px; border-radius:8px; color:white; }
.small-muted { color:#9fb3c8; font-size:12px; }
@media (max-width:1200px) { :root { --trishul-size:480px; } }
@media (max-width:800px) { :root { --trishul-size:320px; } }
</style>
""", unsafe_allow_html=True)

# ---------- SESSION STATE ----------
if 'armed' not in st.session_state:
    st.session_state.armed = False
if 'stop_requested' not in st.session_state:
    st.session_state.stop_requested = False
if 'last_summary' not in st.session_state:
    st.session_state.last_summary = None
if 'log' not in st.session_state:
    st.session_state.log = []

# ---------- HELPERS ----------
def safe_create_exchange(name, api_key=None, secret=None):
    try:
        kwargs = {'enableRateLimit': True}
        if api_key: kwargs['apiKey'] = api_key
        if secret: kwargs['secret'] = secret
        inst = ccxt.__dict__[name](**kwargs)
        try:
            inst.load_markets()
        except Exception:
            pass
        return inst, None
    except Exception as e:
        logging.exception("exchange init")
        return None, str(e)

def fetch_price(inst, symbol):
    try:
        if not getattr(inst, 'markets', None):
            inst.load_markets()
        if symbol not in inst.markets:
            return None
        tick = inst.fetch_ticker(symbol)
        val = tick.get('last') or tick.get('close')
        return float(val) if val is not None else None
    except Exception as e:
        logging.debug(f"price fetch error {getattr(inst,'id',None)} {symbol}: {e}")
        return None

def get_taker_fee(inst, symbol):
    try:
        m = inst.markets.get(symbol)
        if m:
            fee = m.get('taker') or m.get('takerFee')
            if fee: return float(fee)
    except Exception:
        pass
    try:
        return float(inst.fees.get('trading', {}).get('taker', 0.001))
    except Exception:
        return 0.001

def get_withdraw_fee_base(inst, base):
    try:
        fees = getattr(inst, 'fees', {})
        fee = fees.get('funding', {}).get('withdraw', {}).get(base)
        if fee: return float(fee)
    except Exception:
        pass
    return 0.0005

def round_amount(inst, symbol, amt):
    try:
        m = inst.markets.get(symbol)
        if not m: return amt
        prec = m.get('precision', {}).get('amount')
        if prec is None: return amt
        q = Decimal(amt).quantize(Decimal(10) ** -prec, rounding=ROUND_DOWN)
        return float(q)
    except Exception:
        return amt

def compute_metrics(price_buy, price_sell, taker_buy, taker_sell, withdraw_base, slippage):
    buy_fee = price_buy * taker_buy
    withdraw_quote = withdraw_base * price_buy
    buy_cost = price_buy + buy_fee + withdraw_quote
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

# ---------- UI: Inputs ----------
st.header("Arbitrage Dashboard")   # plain title — no emoji prefix

col1, col2, col3 = st.columns([2,2,1])
with col1:
    buy_exchange = st.selectbox("Buy Exchange", EXCHANGES, index=0)
with col2:
    sell_exchange = st.selectbox("Sell Exchange", EXCHANGES, index=1)
with col3:
    poll_interval = st.number_input("Poll (s)", min_value=2, max_value=60, value=DEFAULT_POLL)

c1, c2 = st.columns(2)
with c1:
    base = st.selectbox("Base Asset", BASE_ASSETS, index=0)
with c2:
    quote = st.selectbox("Quote Currency", QUOTES, index=0)

symbol = f"{base}/{quote}"

r1, r2 = st.columns(2)
with r1:
    investment_usd = st.selectbox("Investment (USD)", INVESTMENTS, index=2)
with r2:
    profit_threshold_pct = st.slider("Min profit threshold (%)", 0.1, 10.0, 1.0, step=0.1)

sim_mode = st.checkbox("Simulation Mode (recommended)", value=True)

st.markdown("---")

api_col1, api_col2 = st.columns(2)
with api_col1:
    buy_api = st.text_input(f"{buy_exchange.upper()} API Key", type="password")
    buy_secret = st.text_input(f"{buy_exchange.upper()} Secret", type="password")
with api_col2:
    sell_api = st.text_input(f"{sell_exchange.upper()} API Key", type="password")
    sell_secret = st.text_input(f"{sell_exchange.upper()} Secret", type="password")

st.markdown("---")

act1, act2 = st.columns(2)
with act1:
    perform_btn = st.button("▶️ Perform (arm bot)")
with act2:
    stop_btn = st.button("⛔ Stop Performing")

price_box = st.empty()
metrics_box = st.empty()
status_box = st.empty()
log_box = st.empty()

# ---------- core evaluation ----------
def evaluate_once(buy_inst, sell_inst, symbol, investment, slippage):
    price_buy = fetch_price(buy_inst, symbol)
    price_sell = fetch_price(sell_inst, symbol)
    if price_buy is None or price_sell is None:
        return None, "Price unavailable for symbol on one or both exchanges."
    taker_buy = get_taker_fee(buy_inst, symbol) or 0.001
    taker_sell = get_taker_fee(sell_inst, symbol) or 0.001
    withdraw_base = get_withdraw_fee_base(buy_inst, base)
    metrics = compute_metrics(price_buy, price_sell, taker_buy, taker_sell, withdraw_base, slippage)
    base_amt = investment / price_buy if price_buy > 0 else 0
    base_amt_rounded = round_amount(buy_inst, symbol, base_amt)
    if base_amt_rounded <= 0:
        return None, "Trade amount zero after rounding; increase investment."
    scaled_net = metrics['net_after_slippage'] * base_amt_rounded
    scaled_pct = (scaled_net / (price_buy * base_amt_rounded) * 100) if (price_buy * base_amt_rounded) > 0 else 0.0
    summary = {
        'price_buy': price_buy,
        'price_sell': price_sell,
        'taker_buy': taker_buy,
        'taker_sell': taker_sell,
        'withdraw_base': withdraw_base,
        'metrics': metrics,
        'base_amount_rounded': base_amt_rounded,
        'scaled_net': scaled_net,
        'scaled_pct': scaled_pct
    }
    return summary, None

def render_summary(summary):
    if not summary:
        return
    pb = summary['price_buy']; ps = summary['price_sell']
    price_md = f"""
    <div class='status-card'>
    <h3>📊 Prices & Fees — {symbol}</h3>
    <b>Buy on {buy_exchange.upper()}</b>: ${pb:.2f} &nbsp;&nbsp; <b>Sell on {sell_exchange.upper()}</b>: ${ps:.2f}<br>
    <small class='small-muted'>Buy taker: {summary['taker_buy']*100:.3f}% • Sell taker: {summary['taker_sell']*100:.3f}% • Withdraw(base): {summary['withdraw_base']}</small>
    </div>
    """
    price_box.markdown(price_md, unsafe_allow_html=True)

    net_unit = summary['metrics']['net_after_slippage']
    scaled = summary['scaled_net']; pct = summary['scaled_pct']
    metrics_md = f"""
    <div class='metric'>
    <h3>💰 Profit Estimate</h3>
    Net per 1 {base}: ${net_unit:.6f}<br>
    Investment: ${investment_usd} → ~{summary['base_amount_rounded']:.6f} {base}<br>
    <b>Estimated net profit:</b> ${scaled:.2f} ({pct:.3f}%)
    </div>
    """
    metrics_box.markdown(metrics_md, unsafe_allow_html=True)

    if scaled > 0 and pct >= profit_threshold_pct:
        status_box.markdown(f"<div class='success'>✅ Opportunity — est net ${scaled:.2f} ({pct:.3f}%) meets threshold {profit_threshold_pct}%</div>", unsafe_allow_html=True)
    elif scaled > 0:
        status_box.markdown(f"<div class='status-card'>⚠️ Positive but below threshold: ${scaled:.2f} ({pct:.3f}%)</div>", unsafe_allow_html=True)
    else:
        status_box.markdown(f"<div class='error'>❌ Not profitable: ${scaled:.2f} ({pct:.3f}%)</div>", unsafe_allow_html=True)

# ---------- init exchanges (read-only allowed) ----------
buy_inst, berr = safe_create_exchange(buy_exchange, buy_api or None, buy_secret or None)
sell_inst, serr = safe_create_exchange(sell_exchange, sell_api or None, sell_secret or None)
if berr:
    st.error(f"Failed to init buy exchange {buy_exchange}: {berr}")
    st.stop()
if serr:
    st.error(f"Failed to init sell exchange {sell_exchange}: {serr}")
    st.stop()

# ---------- buttons behavior ----------
if perform_btn:
    if not sim_mode and not (buy_api and buy_secret and sell_api and sell_secret):
        st.error("For REAL execution: provide API+Secret for both exchanges or enable Simulation Mode.")
    else:
        st.session_state.armed = True
        st.session_state.stop_requested = False
        st.success("🟢 Auto-perform ARMED. Bot will monitor and execute when criteria met.")

if stop_btn:
    st.session_state.armed = False
    st.session_state.stop_requested = True
    st.warning("⛔ Auto-perform stopped by user.")

# ---------- auto-monitor iteration ----------
if st.session_state.armed and not st.session_state.stop_requested:
    status_box.info("🔁 Monitoring for opportunities...")
    summary, err = evaluate_once(buy_inst, sell_inst, symbol, investment_usd, DEFAULT_SLIPPAGE)
    if err:
        status_box.error(err)
        time.sleep(poll_interval)
        st.experimental_rerun()
    else:
        render_summary(summary)
        st.session_state.last_summary = summary
        st.session_state.log.append(f"Checked {symbol} buy:{buy_exchange} sell:{sell_exchange} net:${summary['scaled_net']:.2f}")
        log_box.text("\n".join(st.session_state.log[-12:]))

        scaled = summary['scaled_net']; pct = summary['scaled_pct']
        if scaled > 0 and pct >= profit_threshold_pct:
            # Opportunity detected
            if sim_mode:
                st.success(f"🔔 PROFIT DETECTED (SIMULATION) — ${scaled:.2f} ({pct:.3f}%). Simulating execution.")
                st.session_state.log.append(f"Simulated execution {symbol} net ${scaled:.2f}")
                st.session_state.armed = False
                time.sleep(1)
                st.experimental_rerun()
            else:
                buy_exec, berr2 = safe_create_exchange(buy_exchange, buy_api, buy_secret)
                sell_exec, serr2 = safe_create_exchange(sell_exchange, sell_api, sell_secret)
                if berr2 or serr2 or not buy_exec or not sell_exec:
                    status_box.error(f"Auth init failed before execution. buy_err={berr2}, sell_err={serr2}")
                    st.session_state.armed = False
                    st.experimental_rerun()
                final, ferr = evaluate_once(buy_exec, sell_exec, symbol, investment_usd, DEFAULT_SLIPPAGE)
                if ferr or not final:
                    status_box.error("Final re-check failed; aborting execution.")
                    time.sleep(poll_interval)
                    st.experimental_rerun()
                final_scaled = final['scaled_net']; final_pct = final['scaled_pct']
                if final_scaled <= 0 or final_pct < profit_threshold_pct:
                    status_box.warning("Final check not profitable. Continue monitoring.")
                    time.sleep(poll_interval)
                    st.experimental_rerun()
                amt_base = final['base_amount_rounded']
                amt_buy = round_amount(buy_exec, symbol, amt_base)
                amt_sell = round_amount(sell_exec, symbol, amt_base)
                trade_amt = min(amt_buy, amt_sell)
                if trade_amt <= 0:
                    status_box.error("Trade amount invalid after rounding.")
                    st.session_state.armed = False
                    st.experimental_rerun()
                try:
                    status_box.info(f"Placing BUY order for {trade_amt:.8f} {base} on {buy_exchange.upper()} ...")
                    buy_order = buy_exec.create_market_order(symbol, 'buy', trade_amt)
                    status_box.write("Buy response:", buy_order)
                except Exception as e:
                    status_box.error(f"BUY failed: {e}")
                    st.session_state.armed = False
                    st.experimental_rerun()
                try:
                    status_box.info(f"Placing SELL order for {trade_amt:.8f} {base} on {sell_exchange.upper()} ...")
                    sell_order = sell_exec.create_market_order(symbol, 'sell', trade_amt)
                    status_box.write("Sell response:", sell_order)
                except Exception as e:
                    status_box.error(f"SELL failed: {e}")
                    st.session_state.armed = False
                    st.experimental_rerun()
                st.success(f"✅ Auto-executed: {trade_amt:.8f} {base}. Est net ${final_scaled:.2f}")
                st.session_state.log.append(f"Executed {trade_amt:.8f} {base} buy:{buy_exchange} sell:{sell_exchange} net:${final_scaled:.2f}")
                st.session_state.armed = False
                time.sleep(1)
                st.experimental_rerun()
        else:
            time.sleep(poll_interval)
            if st.session_state.stop_requested:
                st.session_state.armed = False
                st.session_state.stop_requested = False
                st.warning("⛔ Auto-perform stopped.")
                st.experimental_rerun()
            st.experimental_rerun()

# ---------- show last summary & logs ----------
if not st.session_state.armed:
    if st.session_state.last_summary:
        render_summary(st.session_state.last_summary)
    else:
        price_box.info("No checks yet. Click ▶️ Perform to arm the bot (Simulation Mode recommended).")
    log_box.text("\n".join(st.session_state.log[-12:]))

st.markdown("---")
st.markdown("**Safety note:** The bot re-checks prices immediately before execution. Markets move fast — test in Simulation Mode and use small amounts first.")
