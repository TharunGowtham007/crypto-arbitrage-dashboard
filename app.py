# app.py
import ccxt
import streamlit as st
import time
import logging
from decimal import Decimal, ROUND_DOWN

# ---------------- Basic config ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")

# ---------------- Lists (edit if you want) ----------------
EXCHANGES = ["binance", "binanceus", "kucoin", "kraken", "coinbase", "okx", "gate", "bitfinex", "bybit"]
CRYPTOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT"]
INVESTMENTS = [100, 250, 500, 1000, 5000, 10000]

DEFAULT_POLL = 5
DEFAULT_SLIPPAGE = 0.005

# ---------------- Styling (faint golden trishul, white accents) ----------------
st.markdown(r"""
<style>
:root { --trishul-size: 740px; }
html::before{
  content: "";
  position: fixed;
  left: 50%;
  top: 44%;
  transform: translate(-50%,-50%);
  width: var(--trishul-size);
  height: var(--trishul-size);
  background-image: url("https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg");
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  opacity: 0.06;
  filter: hue-rotate(15deg) saturate(1.1) drop-shadow(0 8px 30px rgba(0,0,0,0.45));
  z-index: -1;
  pointer-events: none;
}
div[data-testid="stAppViewContainer"] { background: linear-gradient(180deg,#ffffff,#e8f3ff 40%); color: #071224; }
.stApp { position: relative; z-index: 1; padding: 18px 22px; border-radius: 10px; }
h1 { color:#071224; margin-bottom: 6px; font-weight:700; }
.card { background: rgba(7,18,36,0.03); border-radius:12px; padding:12px; box-shadow: 0 6px 18px rgba(0,0,0,0.06); }
.metric-buy { background: linear-gradient(90deg, rgba(0,150,75,0.08), rgba(0,150,75,0.03)); padding:12px; border-radius:8px; }
.metric-sell { background: linear-gradient(90deg, rgba(220,50,50,0.08), rgba(220,50,50,0.03)); padding:12px; border-radius:8px; }
.small-muted { color:#4b6170; font-size:13px; }
.log-box { max-height:260px; overflow:auto; padding:8px; background: rgba(255,255,255,0.85); border-radius:8px; color:#071224; }
.btn { border-radius:8px; padding:8px 14px; font-weight:600; }
.btn-perform { background: linear-gradient(90deg,#00b09b,#96c93d); color:white; }
.btn-stop { background: linear-gradient(90deg,#ff6b6b,#ff3b3b); color:white; }
</style>
""", unsafe_allow_html=True)

# ---------------- Session ----------------
if "armed" not in st.session_state: st.session_state.armed = False
if "stop_requested" not in st.session_state: st.session_state.stop_requested = False
if "last_summary" not in st.session_state: st.session_state.last_summary = None
if "log" not in st.session_state: st.session_state.log = []

# ---------------- Helpers ----------------
def safe_init_exchange(name, api_key=None, secret=None):
    try:
        kwargs = {"enableRateLimit": True}
        if api_key: kwargs["apiKey"] = api_key
        if secret: kwargs["secret"] = secret
        inst = ccxt.__dict__[name](**kwargs)
        try:
            inst.load_markets()
        except Exception:
            pass
        return inst, None
    except Exception as e:
        logging.debug(f"init {name} failed: {e}")
        return None, str(e)

def fetch_price(inst, symbol):
    try:
        if not getattr(inst, "markets", None):
            inst.load_markets()
        if symbol not in inst.markets:
            return None
        t = inst.fetch_ticker(symbol)
        p = t.get("last") or t.get("close")
        return float(p) if p is not None else None
    except Exception as e:
        logging.debug(f"fetch_price error {getattr(inst,'id',None)} {symbol}: {e}")
        return None

def estimate_taker(inst, symbol):
    try:
        m = inst.markets.get(symbol)
        if m:
            fee = m.get("taker") or m.get("takerFee")
            if fee: return float(fee)
    except Exception:
        pass
    try:
        return float(inst.fees.get("trading", {}).get("taker", 0.001))
    except Exception:
        return 0.001

def get_withdraw_fee_base(inst, base):
    try:
        fees = getattr(inst, "fees", {})
        fee = fees.get("funding", {}).get("withdraw", {}).get(base)
        if fee: return float(fee)
    except Exception:
        pass
    return 0.0005

def round_amount(inst, symbol, amt):
    try:
        m = inst.markets.get(symbol)
        if not m: return amt
        prec = m.get("precision", {}).get("amount")
        if prec is None: return amt
        q = Decimal(amt).quantize(Decimal(10) ** -prec, rounding=ROUND_DOWN)
        return float(q)
    except Exception:
        return amt

def compute_metrics(price_buy, price_sell, taker_buy, taker_sell, withdraw_base, slippage):
    buy_fee_quote = price_buy * taker_buy
    withdraw_quote = withdraw_base * price_buy
    buy_cost = price_buy + buy_fee_quote + withdraw_quote
    sell_revenue = price_sell * (1 - taker_sell)
    gross_profit = sell_revenue - price_buy
    net_profit = sell_revenue - buy_cost
    slippage_cost = abs(gross_profit) * slippage
    net_after_slippage = net_profit - slippage_cost
    return {
        "buy_cost": buy_cost,
        "sell_revenue": sell_revenue,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "slippage_cost": slippage_cost,
        "net_after_slippage": net_after_slippage
    }

# ---------------- UI Inputs ----------------
st.title("Arbitrage Dashboard")
st.markdown('<div class="small-muted">Dark + white hybrid theme. Trishul is a faint watermark behind UI.</div>', unsafe_allow_html=True)
st.markdown("")

left, right = st.columns([2,1])
with left:
    buy_ex = st.selectbox("Buy Exchange", EXCHANGES, index=0)
    sell_ex = st.selectbox("Sell Exchange", EXCHANGES, index=1)
with right:
    crypto = st.selectbox("Crypto Pair", CRYPTOS, index=0)
    investment = st.selectbox("Investment (USD)", INVESTMENTS, index=2)

st.markdown("---")

# API fields (explicit)
st.subheader("API Keys (for real trading)")
api_c1, api_c2 = st.columns(2)
with api_c1:
    buy_api = st.text_input(f"{buy_ex.upper()} API Key", type="password", key=f"{buy_ex}_api")
    buy_secret = st.text_input(f"{buy_ex.upper()} Secret", type="password", key=f"{buy_ex}_sec")
with api_c2:
    sell_api = st.text_input(f"{sell_ex.upper()} API Key", type="password", key=f"{sell_ex}_api")
    sell_secret = st.text_input(f"{sell_ex.upper()} Secret", type="password", key=f"{sell_ex}_sec")

st.markdown("---")
c1, c2, c3 = st.columns([1,1,1])
with c1:
    profit_threshold_pct = st.slider("Minimum profit threshold (%)", 0.1, 10.0, 1.0, step=0.1)
with c2:
    slippage_input = st.number_input("Slippage estimate (%)", min_value=0.0, max_value=5.0, value=DEFAULT_SLIPPAGE*100.0, step=0.1)
with c3:
    sim_mode = st.checkbox("Simulation Mode (recommended)", value=True)

slippage = slippage_input / 100.0

st.markdown("---")
act1, act2 = st.columns(2)
with act1:
    perform_btn = st.button("▶️ Perform", key="perform")
with act2:
    stop_btn = st.button("⛔ Stop Performing", key="stop")

price_ph = st.empty()
metrics_ph = st.empty()
status_ph = st.empty()
log_ph = st.empty()

# ---------------- Initialize exchanges (public if no API) ----------------
buy_inst, buy_err = safe_init_exchange(buy_ex, buy_api or None, buy_secret or None)
sell_inst, sell_err = safe_init_exchange(sell_ex, sell_api or None, sell_secret or None)

# show warnings if any (not fatal)
if buy_err:
    st.warning(f"{buy_ex.upper()} init warning: {buy_err}")
if sell_err:
    st.warning(f"{sell_ex.upper()} init warning: {sell_err}")

# ---------------- Button behavior ----------------
if perform_btn:
    if not sim_mode and not (buy_api and buy_secret and sell_api and sell_secret):
        st.error("To run in REAL mode you must provide API & Secret for both exchanges or enable Simulation Mode.")
    else:
        st.session_state.armed = True
        st.session_state.stop_requested = False
        mode = "SIMULATION" if sim_mode else "REAL"
        st.success(f"🟢 Bot ARMED ({mode}). Monitoring for opportunities...")

if stop_btn:
    st.session_state.armed = False
    st.session_state.stop_requested = True
    st.warning("⛔ Bot stopped by user.")

# ---------------- Core evaluation ----------------
def evaluate_once(buy_inst_local, sell_inst_local):
    price_buy = fetch_price(buy_inst_local, crypto) if buy_inst_local else None
    price_sell = fetch_price(sell_inst_local, crypto) if sell_inst_local else None
    if price_buy is None or price_sell is None:
        return None, "Price unavailable on one or both exchanges for symbol " + crypto
    taker_buy = estimate_taker(buy_inst_local, crypto) if buy_inst_local else 0.001
    taker_sell = estimate_taker(sell_inst_local, crypto) if sell_inst_local else 0.001
    withdraw_base = get_withdraw_fee_base(buy_inst_local, crypto.split("/")[0]) if buy_inst_local else 0.0005
    metrics = compute_metrics(price_buy, price_sell, taker_buy, taker_sell, withdraw_base, slippage)
    base_amount = investment / price_buy if price_buy > 0 else 0
    base_amount_rounded = round_amount(buy_inst_local, crypto, base_amount) if buy_inst_local else base_amount
    if base_amount_rounded <= 0:
        return None, "Trade amount is zero after rounding; increase investment"
    scaled_net = metrics["net_after_slippage"] * base_amount_rounded
    scaled_pct = (scaled_net / (price_buy * base_amount_rounded) * 100) if (price_buy * base_amount_rounded) > 0 else 0.0
    summary = {
        "price_buy": price_buy,
        "price_sell": price_sell,
        "taker_buy": taker_buy,
        "taker_sell": taker_sell,
        "withdraw_base": withdraw_base,
        "metrics": metrics,
        "base_amount_rounded": base_amount_rounded,
        "scaled_net": scaled_net,
        "scaled_pct": scaled_pct
    }
    return summary, None

def render_summary(summary):
    pb = summary["price_buy"]; ps = summary["price_sell"]
    price_ph.markdown(f"""
    <div class="card">
      <div style="display:flex;gap:12px;align-items:center;">
        <div style="flex:1">
          <div class="metric-buy"><h4 style="margin:0">Buy — {buy_ex.upper()}</h4><p style="font-size:18px;margin:2px">${pb:,.2f}</p></div>
        </div>
        <div style="flex:1">
          <div class="metric-sell"><h4 style="margin:0">Sell — {sell_ex.upper()}</h4><p style="font-size:18px;margin:2px">${ps:,.2f}</p></div>
        </div>
        <div style="flex:1">
          <div class="card"><h4 style="margin:0">Spread</h4><p style="font-size:18px;margin:2px">{summary['scaled_pct']:.3f}%</p></div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    m = summary["metrics"]
    metrics_ph.markdown(f"""
      <div class="card">
        <b>Net per 1 {crypto.split('/')[0]} after fees & slippage:</b> ${m['net_after_slippage']:.6f}<br>
        <b>Investment:</b> ${investment} → ~{summary['base_amount_rounded']:.6f} {crypto.split('/')[0]}<br>
        <b>Estimated net profit:</b> ${summary['scaled_net']:.2f} ({summary['scaled_pct']:.3f}%)
      </div>
    """, unsafe_allow_html=True)

# ---------------- Auto-monitor (single-iteration style; safe rerun) ----------------
if st.session_state.armed and not st.session_state.stop_requested:
    status_ph.info("🔁 Monitoring for opportunities...")
    buy_local = buy_inst if buy_inst else safe_init_exchange(buy_ex)[0]
    sell_local = sell_inst if sell_inst else safe_init_exchange(sell_ex)[0]

    if not buy_local or not sell_local:
        status_ph.error("Exchange initialization failed for one or both exchanges. Try switching exchanges or use public endpoints.")
        st.session_state.armed = False
        st.session_state.stop_requested = False
    else:
        summary, err = evaluate_once(buy_local, sell_local)
        if err:
            status_ph.error(err)
            st.session_state.log.append(f"Check failed: {err}")
            time.sleep(DEFAULT_POLL)
            st.experimental_rerun()
        else:
            render_summary(summary)
            st.session_state.last_summary = summary
            st.session_state.log.append(f"Checked {crypto} buy:{buy_ex} sell:{sell_ex} net:${summary['scaled_net']:.2f} ({summary['scaled_pct']:.3f}%)")
            log_ph.text("\n".join(st.session_state.log[-12:]))

            scaled_net = summary["scaled_net"]; pct = summary["scaled_pct"]
            if scaled_net > 0 and pct >= profit_threshold_pct:
                if sim_mode:
                    status_ph.success(f"🔔 PROFIT DETECTED (SIM) — ${scaled_net:.2f} ({pct:.3f}%). Simulated execution done.")
                    st.session_state.log.append(f"Simulated exec {crypto} net ${scaled_net:.2f}")
                    st.session_state.armed = False
                    time.sleep(1)
                    st.experimental_rerun()
                else:
                    buy_exec, berr = safe_init_exchange(buy_ex, buy_api, buy_secret)
                    sell_exec, serr = safe_init_exchange(sell_ex, sell_api, sell_secret)
                    if berr or serr or not buy_exec or not sell_exec:
                        status_ph.error(f"Auth init failed before execution. buy_err={berr}, sell_err={serr}")
                        st.session_state.armed = False
                        st.experimental_rerun()
                    final_summary, ferr = evaluate_once(buy_exec, sell_exec)
                    if ferr or not final_summary:
                        status_ph.error("Final re-check failed; aborting execution.")
                        time.sleep(DEFAULT_POLL)
                        st.experimental_rerun()
                    final_scaled = final_summary["scaled_net"]; final_pct = final_summary["scaled_pct"]
                    if final_scaled <= 0 or final_pct < profit_threshold_pct:
                        status_ph.warning("Final check not profitable. Continue monitoring.")
                        time.sleep(DEFAULT_POLL)
                        st.experimental_rerun()
                    amt_base = final_summary["base_amount_rounded"]
                    amt_buy = round_amount(buy_exec, crypto, amt_base)
                    amt_sell = round_amount(sell_exec, crypto, amt_base)
                    trade_amt = min(amt_buy, amt_sell)
                    if trade_amt <= 0:
                        status_ph.error("Trade amount invalid after rounding. Aborting.")
                        st.session_state.armed = False
                        st.experimental_rerun()
                    try:
                        status_ph.info(f"Placing BUY market order for {trade_amt:.8f} {crypto.split('/')[0]} on {buy_ex.upper()} ...")
                        buy_order = buy_exec.create_market_order(crypto, 'buy', trade_amt)
                        status_ph.write("Buy response:", buy_order)
                    except Exception as e:
                        status_ph.error(f"BUY order failed: {e}")
                        st.session_state.armed = False
                        st.experimental_rerun()
                    try:
                        status_ph.info(f"Placing SELL market order for {trade_amt:.8f} {crypto.split('/')[0]} on {sell_ex.upper()} ...")
                        sell_order = sell_exec.create_market_order(crypto, 'sell', trade_amt)
                        status_ph.write("Sell response:", sell_order)
                    except Exception as e:
                        status_ph.error(f"SELL order failed: {e}")
                        st.session_state.armed = False
                        st.experimental_rerun()
                    st.success(f"✅ Auto-executed arbitrage: {trade_amt:.8f} {crypto.split('/')[0]}. Est net ${final_scaled:.2f} ({final_pct:.3f}%)")
                    st.session_state.log.append(f"Executed {trade_amt:.8f} {crypto.split('/')[0]} buy:{buy_ex} sell:{sell_ex} net:${final_scaled:.2f}")
                    st.session_state.armed = False
                    time.sleep(1)
                    st.experimental_rerun()
            else:
                time.sleep(DEFAULT_POLL)
                if st.session_state.stop_requested:
                    st.session_state.armed = False
                    st.session_state.stop_requested = False
                    st.warning("⛔ Auto-perform stopped.")
                    st.experimental_rerun()
                st.experimental_rerun()

# ---------------- Show last summary & logs ----------------
if not st.session_state.armed:
    if st.session_state.last_summary:
        render_summary(st.session_state.last_summary)
    else:
        price_ph.info("No checks yet. Click ▶️ Perform to arm the bot (Simulation Mode recommended).")
    log_ph.text("\n".join(st.session_state.log[-12:]))

st.markdown("---")
st.markdown("**Safety note:** Re-checks are performed immediately before execution. Markets move fast — test in Simulation Mode & use small amounts first.")
