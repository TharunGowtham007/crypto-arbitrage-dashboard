# app.py
import ccxt
import time
import logging
import streamlit as st
from decimal import Decimal, ROUND_DOWN

# --------------------------- CONFIG ----------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

AVAILABLE_EXCHANGES = [
    'binance', 'coinbase', 'kraken', 'kucoin', 'okx', 'gate', 'bitfinex', 'huobi', 'bybit', 'bitstamp', 'mexc'
]
AVAILABLE_CRYPTOS = [
    'BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'LTC', 'DOT', 'LINK', 'AVAX', 'DOGE'
]
AVAILABLE_QUOTE_CURRENCIES = ['USDT', 'USD', 'INR', 'EUR', 'GBP']
AVAILABLE_AMOUNTS = [100, 250, 500, 1000, 5000, 10000]

DEFAULT_SLIPPAGE = 0.005  # 0.5%
DEFAULT_POLL = 5  # seconds

st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")

# --------------------------- STYLING (trishul background & visuals) ----------------------------
st.markdown("""
<style>
/* Big faint trishul (using trident emoji) in background */
body::before {
  content: "🔱";
  position: fixed;
  left: 50%;
  top: 25%;
  transform: translate(-50%, -25%) scale(9);
  font-size: 40px;
  opacity: 0.04;
  z-index: 0;
  pointer-events: none;
  filter: drop-shadow(0 0 20px rgba(0,0,0,0.4));
}

/* app container on top */
.stApp {
  position: relative;
  z-index: 1;
  background: linear-gradient(135deg,#071224,#0f3b5c);
  padding: 22px;
  border-radius: 14px;
  color: #e7f6ff;
}

/* headers and accents */
h1,h2,h3 { color: #8BE7FF; text-shadow: 0 2px 8px rgba(0,0,0,0.6); }
.stButton>button { background: linear-gradient(90deg,#00b09b,#96c93d); color:#012; font-weight:700; border-radius:8px; padding:8px 16px; }
.status-card { background: linear-gradient(145deg,#0b2230,#133a4d); padding:12px; border-radius:12px; margin-bottom:10px; color: #eaf9ff; }
.metric { background: linear-gradient(90deg,#022b3a,#0b4560); padding:12px; border-radius:10px; color: #eaf9ff; }
.error { background: linear-gradient(90deg,#7f0000,#ff3b3b); padding:10px; border-radius:8px; color:white; }
.success { background: linear-gradient(90deg,#007f3f,#00ff9d); padding:10px; border-radius:8px; color:black; }
.small-muted { color: #9fb3c8; font-size:12px; }
</style>
""", unsafe_allow_html=True)

# --------------------------- HELPERS ----------------------------
def create_exchange_instance(name, api_key=None, secret=None):
    """Create ccxt exchange instance and load markets; return (inst, err)."""
    try:
        kwargs = {'enableRateLimit': True}
        if api_key:
            kwargs['apiKey'] = api_key
        if secret:
            kwargs['secret'] = secret
        inst = ccxt.__dict__[name](**kwargs)
        inst.load_markets()
        return inst, None
    except Exception as e:
        logging.exception(f"create_exchange_instance error for {name}: {e}")
        return None, str(e)

def safe_fetch_price(exchange, symbol):
    """Return float price or None if cannot fetch."""
    try:
        if not getattr(exchange, 'markets', None):
            exchange.load_markets()
        if symbol not in exchange.markets:
            return None
        ticker = exchange.fetch_ticker(symbol)
        price = ticker.get('last') or ticker.get('close')
        if price is None:
            return None
        return float(price)
    except Exception as e:
        logging.debug(f"safe_fetch_price: {exchange.id} {symbol} fetch error: {e}")
        return None

def get_taker_fee(exchange, symbol):
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

def get_withdraw_fee_base(exchange, base_symbol):
    try:
        fees = getattr(exchange, 'fees', {})
        fee = fees.get('funding', {}).get('withdraw', {}).get(base_symbol)
        if fee:
            return float(fee)
    except Exception:
        pass
    return 0.0005

def round_amount_by_precision(exchange, symbol, amount):
    try:
        m = exchange.markets.get(symbol)
        if not m:
            return amount
        prec = m.get('precision', {}).get('amount')
        if prec is None:
            return amount
        quant = Decimal(amount).quantize(Decimal(10) ** -prec, rounding=ROUND_DOWN)
        return float(quant)
    except Exception:
        return amount

def compute_arbitrage(price_buy, taker_buy, withdraw_fee_base, price_sell, taker_sell, slippage):
    buy_fee_in_quote = price_buy * taker_buy
    withdraw_fee_in_quote = withdraw_fee_base * price_buy
    buy_cost = price_buy + buy_fee_in_quote + withdraw_fee_in_quote
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

# --------------------------- SESSION STATE INIT ----------------------------
if 'auto_perform' not in st.session_state:
    st.session_state.auto_perform = False
if 'stop_requested' not in st.session_state:
    st.session_state.stop_requested = False
if 'last_summary' not in st.session_state:
    st.session_state.last_summary = None
if 'log' not in st.session_state:
    st.session_state.log = []

# --------------------------- MAIN UI & LOGIC ----------------------------
def main():
    st.title("Arbitrage Dashboard")
    st.markdown("Select markets, check opportunities. Use **Arm Auto-Perform** to let the bot wait and execute automatically when profitable. Use **Stop Auto-Perform** to immediately halt.")

    # top controls
    left, mid, right = st.columns([2,2,1])
    with left:
        exchange_buy = st.selectbox("Buy Exchange", AVAILABLE_EXCHANGES, index=0, key="buy_ex")
    with mid:
        exchange_sell = st.selectbox("Sell Exchange", AVAILABLE_EXCHANGES, index=1, key="sell_ex")
    with right:
        poll_interval = st.number_input("Poll (s)", value=DEFAULT_POLL, min_value=2, max_value=60, step=1)

    # crypto/quote/amount/threshold
    c1, c2 = st.columns(2)
    with c1:
        base_asset = st.selectbox("Base Asset", AVAILABLE_CRYPTOS, index=0, key="base")
    with c2:
        quote = st.selectbox("Quote Currency", AVAILABLE_QUOTE_CURRENCIES, index=0, key="quote")
    symbol = f"{base_asset}/{quote}"

    amt_col, thr_col = st.columns(2)
    with amt_col:
        investment_usd = st.selectbox("Investment (USD equivalent)", AVAILABLE_AMOUNTS, index=2)
    with thr_col:
        profit_threshold_pct = st.slider("Min Profit Threshold (%)", min_value=0.1, max_value=10.0, value=1.0, step=0.1)

    # API keys fields
    st.markdown("### API Keys (required for REAL execution)")
    api_c1, api_c2 = st.columns(2)
    with api_c1:
        api_buy_key = st.text_input(f"{exchange_buy.upper()} API Key", type="password", key=f"{exchange_buy}_api")
        api_buy_secret = st.text_input(f"{exchange_buy.upper()} Secret", type="password", key=f"{exchange_buy}_sec")
    with api_c2:
        api_sell_key = st.text_input(f"{exchange_sell.upper()} API Key", type="password", key=f"{exchange_sell}_api")
        api_sell_secret = st.text_input(f"{exchange_sell.upper()} Secret", type="password", key=f"{exchange_sell}_sec")

    # simulation toggle
    sim_mode = st.checkbox("Simulation Mode (recommended)", value=True)
    st.markdown("<div class='small-muted'>In Simulation Mode the app will not place real orders even if keys are provided. Disable to allow real execution.</div>", unsafe_allow_html=True)

    st.markdown("---")

    # action buttons: check, perform now, arm auto-perform, stop
    btn_check, btn_perform, btn_arm, btn_stop = st.columns([1,1,1,1])
    with btn_check:
        do_check = st.button("🔍 Check Opportunity Now")
    with btn_perform:
        do_perform = st.button("💥 Perform Trade (REAL)")
    with btn_arm:
        arm_auto = st.button("🟢 Arm Auto-Perform")
    with btn_stop:
        stop_auto = st.button("⛔ Stop Auto-Perform")

    # placeholders
    price_ph = st.empty()
    metrics_ph = st.empty()
    status_ph = st.empty()
    log_ph = st.empty()

    # initialize exchange instances for fetching (unauthenticated if keys blank)
    buy_inst, buy_err = create_exchange_instance(exchange_buy, api_buy_key or None, api_buy_secret or None)
    sell_inst, sell_err = create_exchange_instance(exchange_sell, api_sell_key or None, api_sell_secret or None)

    if buy_err:
        st.error(f"Error initializing buy exchange {exchange_buy}: {buy_err}")
        return
    if sell_err:
        st.error(f"Error initializing sell exchange {exchange_sell}: {sell_err}")
        return

    # helpers inside main
    def evaluate_once():
        price_buy = safe_fetch_price(buy_inst, symbol)
        price_sell = safe_fetch_price(sell_inst, symbol)
        if price_buy is None or price_sell is None:
            return None, "Could not fetch price(s) for this symbol on selected exchanges."
        taker_buy = get_taker_fee(buy_inst, symbol) or 0.001
        taker_sell = get_taker_fee(sell_inst, symbol) or 0.001
        withdraw_fee_base = get_withdraw_fee_base(buy_inst, base_asset)
        arb = compute_arbitrage(price_buy, taker_buy, withdraw_fee_base, price_sell, taker_sell, DEFAULT_SLIPPAGE)
        base_amount = investment_usd / price_buy if price_buy > 0 else 0
        base_amount_rounded = round_amount_by_precision(buy_inst, symbol, base_amount)
        if base_amount_rounded <= 0:
            return None, "Computed trade amount is zero after rounding to exchange precision."
        scaled_net = arb['net_after_slippage'] * base_amount_rounded
        scaled_profit_pct = (scaled_net / (price_buy * base_amount_rounded)) * 100 if price_buy * base_amount_rounded > 0 else 0.0
        result = {
            'price_buy': price_buy,
            'price_sell': price_sell,
            'taker_buy': taker_buy,
            'taker_sell': taker_sell,
            'withdraw_fee_base': withdraw_fee_base,
            'arb': arb,
            'base_amount': base_amount,
            'base_amount_rounded': base_amount_rounded,
            'scaled_net': scaled_net,
            'scaled_profit_pct': scaled_profit_pct
        }
        return result, None

    def render_result(res):
        if not res:
            return
        p = res
        price_md = f"""
        <div class='status-card'>
        <h3>📊 Prices & Fees — {symbol}</h3>
        <b>Buy on {exchange_buy.upper()}</b>: ${p['price_buy']:.2f} &nbsp;&nbsp; <b>Sell on {exchange_sell.upper()}</b>: ${p['price_sell']:.2f}<br>
        <small class='small-muted'>Buy taker: {p['taker_buy']*100:.3f}% • Sell taker: {p['taker_sell']*100:.3f}% • Withdraw (base): {p['withdraw_fee_base']}</small>
        </div>
        """
        price_ph.markdown(price_md, unsafe_allow_html=True)

        arb = p['arb']
        net_unit = arb['net_after_slippage']
        scaled_net = p['scaled_net']
        pct = p['scaled_profit_pct']
        metric_md = f"""
        <div class='metric'>
        <h3>💰 Profit Estimate</h3>
        Net per 1 {base_asset}: ${net_unit:.6f}<br>
        Investment: ${investment_usd} → base ~ {p['base_amount_rounded']:.6f} {base_asset}<br>
        <b>Estimated net profit:</b> ${scaled_net:.2f} ({pct:.3f}%)
        </div>
        """
        metrics_ph.markdown(metric_md, unsafe_allow_html=True)

        if scaled_net > 0 and pct >= profit_threshold_pct:
            status_ph.markdown(f"<div class='success'>✅ Profitable: Estimated net ${scaled_net:.2f} ({pct:.3f}%) — meets threshold {profit_threshold_pct}%</div>", unsafe_allow_html=True)
        elif scaled_net > 0:
            status_ph.markdown(f"<div class='status-card'>⚠️ Positive estimate ${scaled_net:.2f} ({pct:.3f}%) but below threshold {profit_threshold_pct}%</div>", unsafe_allow_html=True)
        else:
            status_ph.markdown(f"<div class='error'>❌ Not profitable: Estimated net ${scaled_net:.2f} ({pct:.3f}%). Trades will NOT execute.</div>", unsafe_allow_html=True)

    # Handle Check button
    if do_check:
        status_ph.info("Checking latest prices and computing net profit...")
        summary, err = evaluate_once()
        if err:
            status_ph.error(err)
            st.session_state.last_summary = None
        else:
            render_result(summary)
            st.session_state.last_summary = summary
            st.session_state.log.append(f"Checked {symbol} buy:{exchange_buy} sell:{exchange_sell} -> net ${summary['scaled_net']:.2f}")
            log_ph.text("\n".join(st.session_state.log[-10:]))

    # Handle Perform Now button (single-shot)
    if do_perform:
        if sim_mode:
            st.warning("Simulation Mode is ON — disable simulation to perform real trades.")
        else:
            if not (api_buy_key and api_buy_secret and api_sell_key and api_sell_secret):
                st.error("Both exchanges require API key and secret for real trades. Fill API fields first.")
            else:
                status_ph.info("Final pre-trade evaluation (re-fetching latest data)...")
                buy_exec, berr = create_exchange_instance(exchange_buy, api_buy_key, api_buy_secret)
                sell_exec, serr = create_exchange_instance(exchange_sell, api_sell_key, api_sell_secret)
                if berr or serr or not buy_exec or not sell_exec:
                    st.error(f"Auth init error. Buy err: {berr}, Sell err: {serr}")
                else:
                    summary, err = evaluate_once()
                    if err or not summary:
                        st.error("Could not re-evaluate opportunity. Aborting.")
                    else:
                        scaled_net = summary['scaled_net']
                        pct = summary['scaled_profit_pct']
                        if scaled_net <= 0 or pct < profit_threshold_pct:
                            st.error("Not profitable per final check — aborting.")
                        else:
                            amt_base = summary['base_amount_rounded']
                            amt_buy = round_amount_by_precision(buy_exec, symbol, amt_base)
                            amt_sell = round_amount_by_precision(sell_exec, symbol, amt_base)
                            trade_amt = min(amt_buy, amt_sell)
                            if trade_amt <= 0:
                                st.error("Rounded trade amount invalid. Aborting.")
                            else:
                                st.warning(f"About to place REAL market orders for {trade_amt:.6f} {base_asset}. Confirm to proceed.")
                                confirm = st.checkbox("I confirm: place real market BUY then SELL now (I accept risks).")
                                if confirm:
                                    try:
                                        st.info("Placing BUY order...")
                                        buy_order = buy_exec.create_market_order(symbol, 'buy', trade_amt)
                                        st.write("Buy order:", buy_order)
                                    except Exception as e:
                                        st.error(f"BUY failed: {e}")
                                        return
                                    try:
                                        st.info("Placing SELL order...")
                                        sell_order = sell_exec.create_market_order(symbol, 'sell', trade_amt)
                                        st.write("Sell order:", sell_order)
                                    except Exception as e:
                                        st.error(f"SELL failed: {e}")
                                        return
                                    st.success(f"✅ Executed arbitrage for {trade_amt:.6f} {base_asset}.")
                                    st.session_state.log.append(f"Executed trade {trade_amt:.6f} {base_asset} buy:{exchange_buy} sell:{exchange_sell}")
                                    log_ph.text("\n".join(st.session_state.log[-10:]))
                                else:
                                    st.info("User canceled final confirmation.")

    # ARM Auto-Perform: start auto-perform mode
    if arm_auto:
        if sim_mode:
            st.warning("Auto-Perform requires Simulation Mode OFF. Switch it off to allow real execution.")
        else:
            if not (api_buy_key and api_buy_secret and api_sell_key and api_sell_secret):
                st.error("API keys & secrets required for both exchanges to arm auto-perform.")
            else:
                st.session_state.auto_perform = True
                st.session_state.stop_requested = False
                st.success("🟢 Auto-Perform ARMED. The bot will monitor and execute automatically when profitable (this session must stay active).")

    # STOP auto perform immediately
    if stop_auto:
        st.session_state.auto_perform = False
        st.session_state.stop_requested = True
        st.success("⛔ Auto-Perform stopped by user. No further automatic trades will be attempted.")

    # Auto-Perform loop (single iteration per run; uses experimental rerun to continue)
    if st.session_state.auto_perform and not st.session_state.stop_requested:
        # Display status
        status_ph.info("🔁 Auto-Perform is ARMED — monitoring for profitable opportunity...")
        # Evaluate
        summary, err = evaluate_once()
        if err:
            status_ph.error(f"Auto-Perform check failed: {err}")
            # wait and rerun
            time.sleep(poll_interval)
            st.experimental_rerun()
            return
        else:
            render_result(summary)
            st.session_state.last_summary = summary
            st.session_state.log.append(f"AutoCheck {symbol} -> net ${summary['scaled_net']:.2f}")
            log_ph.text("\n".join(st.session_state.log[-10:]))

            # Auto-execute condition
            scaled_net = summary['scaled_net']
            pct = summary['scaled_profit_pct']
            if scaled_net > 0 and pct >= profit_threshold_pct:
                # Recreate authenticated instances (fresh)
                try:
                    buy_exec, berr = create_exchange_instance(exchange_buy, api_buy_key, api_buy_secret)
                    sell_exec, serr = create_exchange_instance(exchange_sell, api_sell_key, api_sell_secret)
                except Exception as e:
                    st.error(f"Auth init failed before auto-exec: {e}")
                    st.session_state.auto_perform = False
                    return

                if berr or serr or not buy_exec or not sell_exec:
                    st.error(f"Auth init failed: buy_err={berr}, sell_err={serr}")
                    st.session_state.auto_perform = False
                    return

                # Final pre-exec re-check
                final_summary, ferr = evaluate_once()
                if ferr or not final_summary:
                    st.error("Final re-check failed; aborting auto-exec.")
                    st.session_state.auto_perform = False
                    return
                final_scaled_net = final_summary['scaled_net']
                final_pct = final_summary['scaled_profit_pct']
                if final_scaled_net <= 0 or final_pct < profit_threshold_pct:
                    st.warning("Final re-check shows not profitable anymore. Aborting auto-exec and continuing monitoring.")
                    # continue monitoring
                    time.sleep(poll_interval)
                    st.experimental_rerun()
                    return

                # compute trade amount and execute
                amt_base = final_summary['base_amount_rounded']
                amt_buy = round_amount_by_precision(buy_exec, symbol, amt_base)
                amt_sell = round_amount_by_precision(sell_exec, symbol, amt_base)
                trade_amt = min(amt_buy, amt_sell)
                if trade_amt <= 0:
                    st.error("Final trade amount invalid. Aborting auto-exec.")
                    st.session_state.auto_perform = False
                    return

                # place orders
                try:
                    st.info("Auto-Perform: placing BUY order (market)...")
                    buy_order = buy_exec.create_market_order(symbol, 'buy', trade_amt)
                    st.write("Buy order response:", buy_order)
                except Exception as e:
                    st.error(f"Auto BUY failed: {e}")
                    st.session_state.auto_perform = False
                    return
                try:
                    st.info("Auto-Perform: placing SELL order (market)...")
                    sell_order = sell_exec.create_market_order(symbol, 'sell', trade_amt)
                    st.write("Sell order response:", sell_order)
                except Exception as e:
                    st.error(f"Auto SELL failed: {e}")
                    st.session_state.auto_perform = False
                    return

                st.success(f"✅ Auto-Performed arbitrage: bought {trade_amt:.6f} {base_asset} on {exchange_buy.upper()} and sold on {exchange_sell.upper()}.")
                st.session_state.log.append(f"AutoExecuted {trade_amt:.6f} {base_asset} buy:{exchange_buy} sell:{exchange_sell}")
                log_ph.text("\n".join(st.session_state.log[-10:]))
                # after execution, stop auto perform
                st.session_state.auto_perform = False
                return
            else:
                # Not profitable — wait and rerun
                time.sleep(poll_interval)
                # check if user pressed Stop during waiting (session_state.stop_requested)
                if st.session_state.stop_requested:
                    st.session_state.auto_perform = False
                    st.success("⛔ Auto-Perform stopped.")
                    return
                st.experimental_rerun()
                return

    # final logs display
    log_ph.text("\n".join(st.session_state.log[-10:]))

if __name__ == "__main__":
    main()
