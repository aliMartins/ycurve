import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# ============================================================
# APP CONFIG & PARAMETERS
# ============================================================
st.set_page_config(page_title="Treasury Curve Screener", layout="centered")

ZN_WEIGHT = 1.0
ZT_WEIGHT = 3.0
Z_LOOKBACK = 120
Z_ENTRY = 1.5
Z_STOP = 2.2
ATR_THRESHOLD = 0.13
SLOPE_LOOKBACK = 5
SLOPE_CAP = 0.10
REAL_WORLD_MULTIPLIER = 2000

st.title("📊 Treasury Curve Screener")
st.subheader("ZN vs ZT Spread Monitoring")


# ============================================================
# LOAD DATA
# ============================================================
@st.cache_data(ttl=3600)  # Refresh data every hour
def load_data():
    start_date = (pd.Timestamp.today() - pd.tseries.offsets.BDay(260)).strftime("%Y-%m-%d")
    tickers = {"ZN": "ZN=F", "ZT": "ZT=F"}

    data = yf.download(
        list(tickers.values()),
        start=start_date,
        interval="1d",
        auto_adjust=True,
        progress=False
    )["Close"]

    data.columns = ["ZN", "ZT"]
    data.dropna(inplace=True)

    df = data.copy()
    df["curve"] = (ZN_WEIGHT * df["ZN"]) - (ZT_WEIGHT * df["ZT"])
    df["tr"] = df["curve"].diff().abs()
    df["atr"] = df["tr"].rolling(20).mean()
    df["ma_z"] = df["curve"].rolling(Z_LOOKBACK).mean()
    df["std_z"] = df["curve"].rolling(Z_LOOKBACK).std()
    df["z"] = (df["curve"] - df["ma_z"]) / df["std_z"]
    df["ma200"] = df["curve"].rolling(200).mean()
    df["ma200_slope"] = df["ma200"].diff(SLOPE_LOOKBACK)

    df["is_lazy_grind"] = (
            (df["curve"] > df["ma200"]) &
            (df["atr"] < ATR_THRESHOLD) &
            (df["ma200_slope"] > 0) &
            (df["ma200_slope"] < SLOPE_CAP)
    )
    return df


try:
    df = load_data()
    today = df.iloc[-1]
except Exception as e:
    st.error(f"Error fetching data: {e}")
    st.stop()

# ============================================================
# SIDEBAR CONTROLS
# ============================================================
st.sidebar.header("Position Settings")
has_pos = st.sidebar.toggle("Do you currently have a position?", value=False)

# ============================================================
# MODE 1: ENTRY SCREENER
# ============================================================
if not has_pos:
    st.info(f"Last Updated: {df.index[-1].date()}")

    signal = "NO TRADE"
    if today["z"] < -Z_ENTRY:
        signal = "LONG FLATTENER (2 ZN / -3 ZT)"
    elif today["z"] > Z_ENTRY:
        if today["is_lazy_grind"]:
            signal = "SHORT STEEPENER — BLOCKED (Lazy Grind)"
        else:
            signal = "SHORT STEEPENER (-2 ZN / 3 ZT)"

    col1, col2, col3 = st.columns(3)
    col1.metric("Curve Value", f"{today['curve']:.4f}")
    col2.metric("Z-Score", f"{today['z']:.2f}")
    col3.metric("ATR", f"{today['atr']:.4f}")

    st.divider()

    if "BLOCKED" in signal:
        st.warning(f"SIGNAL: {signal}")
    elif "NO TRADE" in signal:
        st.write(f"SIGNAL: {signal}")
    else:
        st.success(f"SIGNAL: {signal}")

    with st.expander("Technical Details"):
        st.write(f"Lazy Grind Status: **{bool(today['is_lazy_grind'])}**")
        st.write(f"MA200 Slope: **{today['ma200_slope']:.6f}**")

# ============================================================
# MODE 2: POSITION MONITOR
# ============================================================
else:
    st.sidebar.divider()
    entry_exec = st.sidebar.number_input("Entry Value (curve × $2000)", value=0.0)
    pos_direction = st.sidebar.selectbox("Position Direction", ["Long Flattener", "Short Steepener"])

    direction = 1 if pos_direction == "Long Flattener" else -1

    # Logic implementation
    curve_now = today["curve"]
    z_now = today["z"]
    mu = today["ma_z"]
    sigma = today["std_z"]

    # Execution-space values (preserving original logic)
    curve_exec = (2 * today["ZN"] - 3 * today["ZT"] * 2) * 1000

    unreal_pnl = (curve_exec - entry_exec) if direction == 1 else (entry_exec - curve_exec)

    if direction == 1:  # LONG
        dz_tp = +0.0 - z_now
        dz_stop = -Z_STOP - z_now
    else:  # SHORT
        dz_tp = -1.0 - z_now
        dz_stop = +Z_STOP - z_now

    exec_per_signal = curve_exec / curve_now
    tp_exec = curve_exec + dz_tp * sigma * exec_per_signal
    stop_exec = curve_exec + dz_stop * sigma * exec_per_signal

    # Display Metrics
    st.header(f"Position: {pos_direction}")

    m1, m2, m3 = st.columns(3)
    m1.metric("Unrealized PnL", f"${unreal_pnl:,.2f}")
    m2.metric("Current Z-Score", f"{z_now:,.2f}")
    m3.metric("Current Value ($)", f"${curve_exec:,.2f}")

    st.divider()

    c1, c2 = st.columns(2)
    c1.metric("Take Profit ($)", f"${tp_exec:,.2f}", help="Target: Z=0.0 (Long) or Z=-1.0 (Short)")
    c2.metric("Stop Loss ($)", f"${stop_exec:,.2f}", help=f"Target: |Z| = {Z_STOP}")

    st.write(f"**Live Prices:** ZN: {today['ZN']:,.2f} | ZT: {today['ZT']:,.2f}")
