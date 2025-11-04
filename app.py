import ccxt
import streamlit as st
import time
import logging
import datetime
import pandas as pd

# ------------------------------------------
# BASIC CONFIG
# ------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
st.set_page_config(page_title="Arbitrage Dashboard", layout="wide")

EXCHANGES = ccxt.exchanges

# Common crypto pairs for selectbox
COMMON_CRYPTOS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "SOL/USDT", 
    "XRP/USDT", "DOT/USDT", "DOGE/USDT", "LTC/USDT", "LINK/USDT",
    "MATIC/USDT", "AVAX/USDT", "UNI/USDT", "ALGO/USDT", "VET/USDT",
    "ICP/USDT", "FIL/USDT", "TRX/USDT", "ETC/USDT", "XLM/USDT",
    "Custom"  # Add this for custom input
]

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
        logging.error(f"Failed to initialize {name}: {e}")
        st.warning(f"{name.capitalize()} unavailable. Check API keys or try another exchange.")
        return None

def get_price(ex, sym):
    try:
        t = ex.fetch_ticker(sym)
        return t["last"]
    except Exception as e:
        logging.error(f"Failed to fetch price for {sym} on {ex.id}: {e}")
        return None

def execute_trade(ex, side, symbol, amount, price):
    try:
        order = ex.create_order(symbol, 'limit', side, amount, price)
        return order
    except Exception as e:
        logging.error(f"Trade execution failed: {e}")
        return None

# ------------------------------------------
# CUSTOM STYLE — ENHANCED MATURE GRAPHICS
# ------------------------------------------
st.markdown("""
<style>
body {
    background: linear-gradient(135deg, #000000, #1a1a1a);
    color: #ffffff;
    font-family: "Segoe UI", sans-serif;
    overflow-x: hidden;
    animation: globalFade 1.5s ease-in;
}

@keyframes globalFade {
    from { opacity: 0; transform: scale(0.98); }
    to { opacity: 1; transform: scale(1); }
}

/* Trishul background with enhanced glow and particles */
div[data-testid="stAppViewContainer"] {
    background: url('https://upload.wikimedia.org/wikipedia/commons/3/3b/Trishul_symbol.svg') no-repeat center center fixed;
    background-size: 600px 600px;
    background-blend-mode: soft-light;
    opacity: 0.98;
    background-color ⬤