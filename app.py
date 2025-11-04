# app.py
import ccxt
import time
import logging
from decimal import Decimal, ROUND_DOWN
import streamlit as st

# ----------------- CONFIG -----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

EXCHANGES = ['binance', 'kucoin', 'kraken', 'coinbase', 'okx', 'gate', 'bitfinex', 'huobi', 'bybit', 'bitstamp']
BASE_ASSETS = ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'XRP', 'LTC', 'DOT', 'LINK', 'AVAX', 'DOGE']
QUOTES = ['USDT', 'USD', 'INR', 'EUR', 'BUSD', 'USDC']
INVESTMENTS = [100, 250, 500, 1000, 5000, 10000]

DEFAULT_SLIPPAGE = 0.005   # 0.5%
DEFAULT_POLL = 5           # seconds between checks

# ----------------- PAGE SETUP & SAFE CSS (TRISHUL BACKGROUND) -----------------
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide", page_icon="🔱")

# Use a background DIV with z-index -1 so it never covers UI; use an SVG hosted or emoji as fallback.
st.markdown(r"""
<style>
:root { --trishul-size: 700px; }

html::before {
  content: "";
  position: fixed;
  left: 50%;
  top: 45%;
  transform: translate(-50%, -50%);
  width: var(--trishul-size);
  height: var(--trishul-size);
  background-image: url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg');
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  opacity: 0.06;              /* faint */
  z-index: -1;                /* crucial: behind all UI */
  pointer-events: none;
  filter: drop-shadow(0 8px 30px rgba(0,0,0,0.45));
}

/* App container stays above background */
.stApp {
  position: relative;
  z-index: 1;
  background: linear-gradient(135deg,#071224,#0f3b5c);
  padding: 22px;
  border-radius: 12px;
  color: #e7f6ff;
  box-shadow: 0 8px 40px rgba(2,20,40,0.6);
}

/* Typography + controls */
h1,h2,h3 { color: #8BE7FF; text-shadow: 0 2px 8px rgba(0,0,0,0.6); }
.stButton>button { background: linear-gradient(90deg,#00b09b,#96c93d); color:#012; font-weight:700; border-radius:8px; padding:8px 14px; }
.status-card { background: linear-gradient(145deg,#0b2230,#133a4d); padding:12px; border-radius:10px; color:#eaf9ff; }
.metric { background: linear-gradient(90deg,#022b3a,#0b4560); padding:12px; border-radius:10px; color:#eaf9ff; }
.success { background: linear-gradient(90deg,#007f3f,#00ff9d); padding:10px; border-radius:8px; color:black; }
.error { background: linear-gradient(90deg,#7f0000,#ff3b3b); padding:10px; border-radius:8px; color:white; }
.small-muted { color: #9fb3c8; font-size:12px; }
@media (max-width: 1200px) { :root { --trishul-size: 480px; } }
@media (max-width: 800px) { :root { --trishul-size: 320px; } }
</style>
""", unsafe_allow_html=True)

# ----------------- SESSION STATE -----------------
if 'armed' not in st.session_state: st.session_state.armed = False
if 'stop_requested' not in st.session_state: st.session_state.stop_requested = False
if 'last_summary' not in st.session_state: st.session_state.last_summary = None
if 'log' not in st.session_state: st.session_state.log = []

# ----------------- HELPERS -----------------
def safe_create_exchange(ex_name, api_key=None, secret=None):
    """Create ccxt exchange instance; return (instance, error_str_or_None)."""
    try:
        kwargs = {'enableRateLimit': True}
        if api_key: kwargs['apiKey'] = api_key
        if secret: kwargs['secret'] = secret
        inst = ccxt.__dict__[ex_name](**kwargs)
        # Attempt to load markets but don't fail the whole app if it rate-limits
        try:
            inst.load_markets()
        except Exception:
            pass
        return inst, None
    except Exception as e:
        logging.exception(f"Exchange init failed: {ex_name}")
        return None, str(e)

def fetch_price(exchange_inst, symbol):
    """Return float price or None."""
    try:
        if not getattr(exchange_inst, 'markets', None):
            exchange_inst.load_markets()
        if symbol not in exchange_inst.markets:
            return None
        t = exchange_inst.fetch_ticker(symbol)
        p = t.get('last') or t.get('close')
        return float(p) if p is not None else None
    except Exception as e:
        logging.debug(f"fetch_price error {getattr(exchange_inst,'id',None)} {symbol}: {e}")
        return None

def get_taker_fee(exchange_inst, symbol):
    try:
        m = exchange_inst.markets.get(symbol)
        if m:
            fee = m.get('taker') or m.get('takerFee')
            if fee: return float(fee)
    except Exception:
        pass
    try:
        return float(exchange_inst.fees.get('trading', {}).get('taker', 0.001))
    except Exception:
        return 0.001

def get_withdraw_fee_base(exchange_inst, base_symbol):
    try:
        fees = getattr(exchange_inst, 'fees', {})
        fee = fees.get('funding', {}).get('withdraw', {}).get(base_symbol)
        if fee: return float(fee)
    except Exception:
        pass
    return 0.0005

def round_amount(exchange_inst, symbol, amt):
    try:
        m = exchange_inst.markets.get(symbol)
        if not m: return amt
        prec = m.get('precision', {}).get('amount')
        if prec is None: return amt
        q = Decimal(amt).quantize(Decimal(10) ** -prec, rounding=ROUND_DOWN)
        return float(q)
    except Exception:
        return amt

def compute_metrics(price_buy, price_sell, taker_buy, taker_sell, withdraw_base, slippage):
    buy_fee = price_buy * taker_buy
    withdraw_in_quote = withdraw_base * price_buy
    buy_cost = price_buy + buy_fee + withdraw_in_quote
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

# ----------------- UI: Inputs -----------------
st.header("Arbitrage Dashboard")

c1, c2, c3 = st.columns([2,2,1])
with c1:
    buy_exchange = st.selectbox("Buy Exchange", EXCHANGES, index=0)
with c2:
    sell_exchange = st.selectbox("Sell Exchange", EXCHANGES, index=1)
with c3:
    poll_interval = st.number_input("Poll (s)", min_value=2, max_value=60, value=DEFAULT_POLL)

b1, b2 = st.columns(2)
with b1:
    base = st.selectbox("Base Asset", BASE_ASSETS, index=0)
with b2:
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

act_col1, act_col2 = st.columns(2)
with act_col1:
    perform_btn = st.button("▶️ Perform (arm bot)")
with act_col2:
    stop_btn = st.button("⛔ Stop Performing")

price_box = st.empty()
metrics_box = st.empty()
status_box = st.empty()
log_box = st.empty()

# ----------------- Core evaluation & rendering -----------------
def evaluate_once(buy_inst, sell_inst, symbol, investment, slippage_rate):
    price_buy = fetch_price(buy_inst, symbol)
    price_sell = fetch_price(sell_inst, symbol)
    if price_buy is None or price_sell is None:
        return None, "Price unavailable on one or both exchanges for symbol " + symbol
    taker_buy = get_taker_fee(buy_inst, symbol) or 0.001
    taker_sell = get_taker_fee(sell_inst, symbol) or 0.001
    withdraw_base = get_withdraw_fee_base(buy_inst, base)
    metrics = compute_metrics(price_buy, price_sell, taker_buy, taker_sell, withdraw_base, slippage_rate)
    base_amount = investment / price_buy if price_buy > 0 else 0
    base_amount_rounded = round_amount(buy_inst, symbol, base_amount)
    if base_amount_rounded <= 0:
        return None, "Trade amount is zero after rounding — increase investment"
    scaled_net = metrics['net_after_slippage'] * base_amount_rounded
    scaled_pct = (scaled_net / (price_buy * base_amount_rounded) * 100) if (price_buy * base_amount_rounded) > 0 else 0.0
    summary = {
        'price_buy': price_buy,
        'price_sell': price_sell,
        'taker_buy': taker_buy,
        'taker_sell': taker_sell,
        'withdraw_base': withdraw_base,
        'metrics': metrics,
        'base_amount_rounded': base_amount_rounded,
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
        status_box.markdown(f"<div class='success'>✅ Opportunity — estimated net ${scaled:.2f} ({pct:.3f}%) meets threshold {profit_threshold_pct}%</div>", unsafe_allow_html=True)
    elif scaled > 0:
        status_box.markdown(f"<div class='status-card'>⚠️ Positive but below threshold — ${scaled:.2f} ({pct:.3f}%)</div>", unsafe_allow_html=True)
    else:
        status_box.markdown(f"<div class='error'>❌ Not profitable — estimated net ${scaled:.2f} ({pct:.3f}%)</div>", unsafe_allow_html=True)

# ----------------- Initialize exchange instances (read-only allowed) -----------------
buy_inst, buy_err = safe_create_exchange(buy_exchange, buy_api if buy_api else None, buy_secret if buy_secret else None)
sell_inst, sell_err = safe_create_exchange(sell_exchange, sell_api if sell_api else None, sell_secret if sell_secret else None)

if buy_err:
    st.error(f"Failed to init buy exchange {buy_exchange}: {buy_err}")
    st.stop()
if sell_err:
    st.error(f"Failed to init sell exchange {sell_exchange}: {sell_err}")
    st.stop()

# ----------------- Buttons behavior -----------------
if perform_btn:
    # require keys for real execution; simulation allowed
    if not sim_mode and not (buy_api and buy_secret and sell_api and sell_secret):
        st.error("For real execution you must provide API + Secret for both exchanges or enable Simulation Mode.")
    else:
        st.session_state.armed = True
        st.session_state.stop_requested = False
        mode = "SIMULATION" if sim_mode else "REAL"
        st.success(f"🟢 Auto-perform armed ({mode}). The bot will monitor and auto-execute when profit ≥ threshold.")

if stop_btn:
    st.session_state.armed = False
    st.session_state.stop_requested = True
    st.warning("⛔ Auto-perform stopped by user.")

# ----------------- Auto-monitor loop (single iteration per run; uses experimental_rerun) -----------------
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
            # Opportunity detected — proceed to auto-execute (simulate or real)
            if sim_mode:
                st.success(f"🔔 PROFIT DETECTED (SIMULATION) — ${scaled:.2f} ({pct:.3f}%). Simulating execution now.")
                st.session_state.log.append(f"Simulated execution {symbol} net ${scaled:.2f}")
                st.session_state.armed = False
                time.sleep(1)
                st.experimental_rerun()
            else:
                # create authenticated instances for real execution
                buy_exec, berr = safe_create_exchange(buy_exchange, buy_api, buy_secret)
                sell_exec, serr = safe_create_exchange(sell_exchange, sell_api, sell_secret)
                if berr or serr or not buy_exec or not sell_exec:
                    status_box.error(f"Auth init failed before execution. buy_err={berr}, sell_err={serr}")
                    st.session_state.armed = False
                    st.experimental_rerun()
                # final re-eval
                final, ferr = evaluate_once(buy_exec, sell_exec, symbol, investment_usd, DEFAULT_SLIPPAGE)
                if ferr or not final:
                    status_box.error("Final re-check failed; aborting execution.")
                    time.sleep(poll_interval)
                    st.experimental_rerun()
                final_scaled = final['scaled_net']; final_pct = final['scaled_pct']
                if final_scaled <= 0 or final_pct < profit_threshold_pct:
                    status_box.warning("Final check not profitable. Will continue monitoring.")
                    time.sleep(poll_interval)
                    st.experimental_rerun()
                # compute trade amount and round according to precision
                amt_base = final['base_amount_rounded']
                amt_buy = round_amount(buy_exec, symbol, amt_base)
                amt_sell = round_amount(sell_exec, symbol, amt_base)
                trade_amt = min(amt_buy, amt_sell)
                if trade_amt <= 0:
                    status_box.error("Trade amount invalid after rounding. Aborting.")
                    st.session_state.armed = False
                    st.experimental_rerun()
                # auto-execute: buy then sell (market orders)
                try:
                    status_box.info(f"Placing BUY order for {trade_amt:.8f} {base} on {buy_exchange.upper()} ...")
                    buy_order = buy_exec.create_market_order(symbol, 'buy', trade_amt)
                    status_box.write("Buy response:", buy_order)
                except Exception as e:
                    status_box.error(f"BUY order failed: {e}")
                    st.session_state.armed = False
                    st.experimental_rerun()
                try:
                    status_box.info(f"Placing SELL order for {trade_amt:.8f} {base} on {sell_exchange.upper()} ...")
                    sell_order = sell_exec.create_market_order(symbol, 'sell', trade_amt)
                    status_box.write("Sell response:", sell_order)
                except Exception as e:
                    status_box.error(f"SELL order failed: {e}")
                    st.session_state.armed = False
                    st.experimental_rerun()
                st.success(f"✅ Auto-executed arbitrage: traded {trade_amt:.8f} {base} buy:{buy_exchange} sell:{sell_exchange} est net ${final_scaled:.2f}")
                st.session_state.log.append(f"Executed {trade_amt:.8f} {base} buy:{buy_exchange} sell:{sell_exchange} net:${final_scaled:.2f}")
                st.session_state.armed = False
                time.sleep(1)
                st.experimental_rerun()
        else:
            # not profitable -> sleep and rerun
            time.sleep(poll_interval)
            if st.session_state.stop_requested:
                st.session_state.armed = False
                st.session_state.stop_requested = False
                st.warning("⛔ Auto-perform stopped.")
                st.experimental_rerun()
            st.experimental_rerun()

# ----------------- Show last summary + logs when not armed -----------------
if not st.session_state.armed:
    if st.session_state.last_summary:
        render_summary(st.session_state.last_summary)
    else:
        price_box.info("No checks yet. Click ▶️ Perform to arm the bot (Simulation Mode recommended).")
    log_box.text("\n".join(st.session_state.log[-12:]))

st.markdown("---")
st.markdown("**Safety note:** The bot re-checks prices immediately before executing. Markets move fast — test thoroughly in Simulation Mode and use small funds first.")
