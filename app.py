import streamlit as st
import requests
import yfinance as yf
import pandas as pd
import os
from datetime import datetime

# ==========================================
# PAGE CONFIG & SESSION STATE
# ==========================================
st.set_page_config(page_title="Private Trading Simulator", layout="wide", page_icon="📈")

if 'balance' not in st.session_state:
    st.session_state.balance = 100000.0
if 'positions' not in st.session_state:
    st.session_state.positions = []
if 'last_valid_price' not in st.session_state:
    st.session_state.last_valid_price = {}

# ==========================================
# HYBRID DATA FETCHING ENGINE
# ==========================================
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY")

ASSETS = {
    "Gold (XAUUSD)": {"finnhub": "OANDA:XAU_USD", "yahoo": "GC=F"},
    "Crude Oil (WTI)": {"finnhub": "OANDA:USOIL", "yahoo": "CL=F"}, 
    "EUR/USD": {"finnhub": "OANDA:EUR_USD", "yahoo": "EURUSD=X"},
    "GBP/USD": {"finnhub": "OANDA:GBP_USD", "yahoo": "GBPUSD=X"},
    "US500 (S&P)": {"finnhub": "US500", "yahoo": "^GSPC"}
}

selected_asset_name = st.selectbox("Select Instrument", list(ASSETS.keys()))
symbols = ASSETS[selected_asset_name]

current_price = 0.0
data_source = ""

# Strategy 1: Try Finnhub First (Fastest for Stocks/Crypto)
if FINNHUB_API_KEY:
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbols['finnhub']}&token={FINNHUB_API_KEY}"
        resp = requests.get(url, timeout=4)
        data = resp.json()
        if 'c' in data and isinstance(data['c'], (int, float)) and data['c'] > 0:
            current_price = float(data['c'])
            data_source = "Finnhub (Real-time)"
    except Exception:
        pass

# Strategy 2: Fallback to Yahoo Finance (Reliable for Forex/Commodities)
if current_price == 0:
    try:
        df = yf.download(symbols['yahoo'], period="1d", interval="1m", progress=False, timeout=5)
        if not df.empty and 'Close' in df.columns:
            current_price = float(df['Close'].dropna().iloc[-1])
            data_source = "Yahoo Finance (Fallback)"
    except Exception:
        pass

# Cache last known price to prevent UI flickering
if current_price > 0:
    st.session_state.last_valid_price[selected_asset_name] = current_price
elif selected_asset_name in st.session_state.last_valid_price:
    current_price = st.session_state.last_valid_price[selected_asset_name]
    data_source = "Cached Data"

# ==========================================
# DASHBOARD METRICS
# ==========================================
col1, col2, col3 = st.columns(3)
col1.metric("Current Price", f"{current_price:.4f}" if current_price > 0 else "N/A")
col2.metric("Fake Balance", f"${st.session_state.balance:,.2f}")
col3.metric("Open Positions", len(st.session_state.positions))

if current_price == 0:
    st.error("❌ Unable to fetch live price from any source. Market might be closed.")
else:
    st.caption(f"📡 Data Source: {data_source}")

# ==========================================
# ORDER PANEL
# ==========================================
st.divider()
st.subheader("Place Order")

order_type = st.radio("Direction", ["Market Buy", "Market Sell"], horizontal=True)
lot_size = st.number_input("Lot Size (Units)", min_value=1, max_value=100, value=1)

default_sl = current_price * 0.98 if "Buy" in order_type else current_price * 1.02
default_tp = current_price * 1.02 if "Buy" in order_type else current_price * 0.98

sl_col, tp_col = st.columns(2)
with sl_col:
    sl_price = st.number_input("Stop Loss Price", value=default_sl, step=0.01)
with tp_col:
    tp_price = st.number_input("Take Profit Price", value=default_tp, step=0.01)

execute_btn = st.button("Execute Trade", type="primary", use_container_width=True)

if execute_btn:
    if current_price == 0:
        st.error("Cannot trade: No live price available!")
    elif lot_size * current_price > st.session_state.balance:
        st.error(f"Insufficient Balance! Required: ${lot_size * current_price:,.2f}")
    else:
        st.session_state.balance -= (current_price * lot_size)
        st.session_state.positions.append({
            "asset": selected_asset_name,
            "type": order_type,
            "entry": current_price,
            "lots": lot_size,
            "sl": sl_price,
            "tp": tp_price,
            "time": datetime.now().strftime("%H:%M:%S")
        })
        st.success(f"Executed: {order_type} {lot_size} {selected_asset_name} @ {current_price:.4f}")
        st.rerun()

# ==========================================
# POSITIONS TABLE WITH AUTO SL/TP
# ==========================================
if st.session_state.positions:
    st.divider()
    st.subheader("Open Positions")
    
    pos_df = pd.DataFrame(st.session_state.positions)
    pos_df['current_price'] = current_price
    
    def calc_pnl(row):
        if "Buy" in row['type']:
            return (row['current_price'] - row['entry']) * row['lots']
        return (row['entry'] - row['current_price']) * row['lots']
        
    pos_df['pnl'] = pos_df.apply(calc_pnl, axis=1)
    
    closed_indices = []
    for idx, row in pos_df.iterrows():
        hit_sl = hit_tp = False
        if "Buy" in row['type']:
            if row['current_price'] <= row['sl']: hit_sl = True
            if row['current_price'] >= row['tp']: hit_tp = True
        else:
            if row['current_price'] >= row['sl']: hit_sl = True
            if row['current_price'] <= row['tp']: hit_tp = True
            
        if hit_sl or hit_tp:
            pnl_realized = row['pnl']
            refund = row['entry'] * row['lots']
            st.session_state.balance += (refund + pnl_realized)
            closed_indices.append(idx)
            reason = "STOP LOSS" if hit_sl else "TAKE PROFIT"
            st.toast(f"{reason} Hit: {row['asset']} | P&L: ${pnl_realized:,.2f}", icon="🔔")

    if closed_indices:
        st.session_state.positions = [p for i, p in enumerate(st.session_state.positions) if i not in closed_indices]
        st.rerun()
    
    st.dataframe(pos_df[['asset', 'type', 'entry', 'lots', 'sl', 'tp', 'pnl']], use_container_width=True, hide_index=True)

# ==========================================
# RENDER-FRIENDLY AUTO REFRESH
# ==========================================
# Using meta refresh instead of time.sleep to prevent server timeouts
st.markdown("""
<meta http-equiv="refresh" content="15">
""", unsafe_allow_html=True)
