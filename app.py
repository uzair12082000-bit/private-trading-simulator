import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# ==========================================
# PAGE CONFIG & SESSION STATE INITIALIZATION
# ==========================================
st.set_page_config(page_title="Private Trading Simulator", layout="wide", page_icon="📈")

# Initialize Fake Wallet & Positions only once
if 'balance' not in st.session_state:
    st.session_state.balance = 100000.0
if 'positions' not in st.session_state:
    st.session_state.positions = []
if 'trade_history' not in st.session_state:
    st.session_state.trade_history = []

# ==========================================
# LIVE DATA FETCHING (YAHOO FINANCE)
# ==========================================
ASSETS = {
    "Gold (XAUUSD)": "GC=F",
    "Crude Oil (WTI)": "CL=F", 
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "US500 (S&P)": "^GSPC"
}

selected_asset_name = st.selectbox("Select Instrument", list(ASSETS.keys()))
ticker_code = ASSETS[selected_asset_name]

# Fetch latest data safely
try:
    df = yf.download(ticker_code, period="1d", interval="1m", progress=False)
    current_price = float(df['Close'].iloc[-1]) if not df.empty else 0.0
except Exception:
    current_price = 0.0
    st.warning("⚠️ Market closed or data temporarily unavailable.")

# ==========================================
# DASHBOARD HEADER METRICS
# ==========================================
col1, col2, col3 = st.columns(3)
col1.metric(" Current Price", f"{current_price:.4f}" if current_price > 0 else "N/A")
col2.metric("💳 Fake Balance", f"${st.session_state.balance:,.2f}")
col3.metric("📊 Open Positions", len(st.session_state.positions))

# ==========================================
# ORDER EXECUTION PANEL
# ==========================================
st.divider()
st.subheader("🎯 Place Order")

order_type = st.radio("Direction", ["Market Buy", "Market Sell"], horizontal=True)
lot_size = st.number_input("Lot Size (Units)", min_value=1, max_value=100, value=1)

# Auto-calculate default SL/TP based on direction
default_sl = current_price * 0.98 if "Buy" in order_type else current_price * 1.02
default_tp = current_price * 1.02 if "Buy" in order_type else current_price * 0.98

sl_col, tp_col = st.columns(2)
with sl_col:
    sl_price = st.number_input("Stop Loss Price", value=default_sl, step=0.01)
with tp_col:
    tp_price = st.number_input("Take Profit Price", value=default_tp, step=0.01)

execute_btn = st.button("🚀 Execute Trade", type="primary", use_container_width=True)

if execute_btn:
    if current_price == 0:
        st.error("❌ Cannot trade: No live price available!")
    elif lot_size * current_price > st.session_state.balance:
        st.error(f"❌ Insufficient Balance! Required: ${lot_size * current_price:,.2f}")
    else:
        # Deduct margin from balance
        st.session_state.balance -= (current_price * lot_size)
        
        new_position = {
            "asset": selected_asset_name,
            "type": order_type,
            "entry": current_price,
            "lots": lot_size,
            "sl": sl_price,
            "tp": tp_price,
            "time": datetime.now().strftime("%H:%M:%S")
        }
        st.session_state.positions.append(new_position)
        st.success(f"✅ Executed: {order_type} {lot_size} {selected_asset_name} @ {current_price:.4f}")
        st.rerun()

# ==========================================
# POSITIONS TABLE WITH AUTO SL/TP CHECK
# ==========================================
if st.session_state.positions:
    st.divider()
    st.subheader("📋 Open Positions")
    
    pos_df = pd.DataFrame(st.session_state.positions)
    pos_df['current_price'] = current_price
    
    # Calculate Unrealized P&L
    def calc_pnl(row):
        if "Buy" in row['type']:
            return (row['current_price'] - row['entry']) * row['lots']
        else:
            return (row['entry'] - row['current_price']) * row['lots']
            
    pos_df['pnl'] = pos_df.apply(calc_pnl, axis=1)
    
    # Check and Auto-Close SL/TP
    closed_indices = []
    for idx, row in pos_df.iterrows():
        hit_sl = False
        hit_tp = False
        
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
            st.toast(f"🔔 {reason} Hit: {row['asset']} | P&L: ${pnl_realized:,.2f}", icon="🔔")

    # Remove closed positions
    if closed_indices:
        st.session_state.positions = [p for i, p in enumerate(st.session_state.positions) if i not in closed_indices]
        st.rerun()
    
    # Display Table with Color Coding
    st.dataframe(
        pos_df[['asset', 'type', 'entry', 'lots', 'sl', 'tp', 'pnl']],
        use_container_width=True,
        column_config={
            "pnl": st.column_config.NumberColumn("P&L ($)", format="$%.2f")
        },
        hide_index=True
    )

# ==========================================
# CHART SECTION
# ==========================================
if not df.empty:
    st.divider()
    st.subheader("📉 Live Chart (1-Minute)")
    st.line_chart(df['Close'], height=400)

# ==========================================
# AUTO REFRESH EVERY 15 SECONDS
# ==========================================
# Using rerun instead of sleep to prevent Render crashes
import time
time.sleep(15)
st.rerun()
