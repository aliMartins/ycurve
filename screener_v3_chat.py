import yfinance as yf
import pandas as pd
import numpy as np

# ============================================================
# PARAMETERS (MATCH BACKTEST)
# ============================================================

ZN_WEIGHT = 1.0
ZT_WEIGHT = 3.0

Z_LOOKBACK = 120
Z_ENTRY = 1.5
Z_STOP = 2.2

ATR_THRESHOLD = 0.13
SLOPE_LOOKBACK = 5
SLOPE_CAP = 0.10

REAL_WORLD_MULTIPLIER = 2000   # 2 ZN : 3 ZT

START_DATE = (pd.Timestamp.today() - pd.tseries.offsets.BDay(260)).strftime("%Y-%m-%d")

# ============================================================
# LOAD DATA
# ============================================================

tickers = {"ZN": "ZN=F", "ZT": "ZT=F"}

data = yf.download(
    list(tickers.values()),
    start=START_DATE,
    interval="1d",
    auto_adjust=True,
    progress=False
)["Close"]

data.columns = ["ZN", "ZT"]
data.dropna(inplace=True)

df = data.copy()

# ============================================================
# CURVE & INDICATORS
# ============================================================

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

today = df.iloc[-1]

# ============================================================
# USER INTERACTION
# ============================================================

print("\nDo you currently have a position? [y/N]")
has_pos = input().strip().lower()

# ============================================================
# MODE 1: ENTRY SCREENER
# ============================================================

if has_pos != "y":

    signal = "NO TRADE"

    if today["z"] < -Z_ENTRY:
        signal = "LONG FLATTENER (2 ZN / -3 ZT)"
    elif today["z"] > Z_ENTRY:
        if today["is_lazy_grind"]:
            signal = "SHORT STEEPENER — BLOCKED (Lazy Grind)"
        else:
            signal = "SHORT STEEPENER (-2 ZN / 3 ZT)"

    print("\n" + "=" * 60)
    print(" DAILY CURVE ENTRY SCREENER ")
    print("=" * 60)
    print(f"Date:        {df.index[-1].date()}")
    print(f"Curve:       {today['curve']:.4f}")
    print(f"Z-Score:     {today['z']:.2f}")
    print(f"ATR:         {today['atr']:.4f}")
    print(f"Lazy Grind:  {bool(today['is_lazy_grind'])}")
    print("-" * 60)
    print(f"SIGNAL: {signal}")
    print("=" * 60)

# ============================================================
# MODE 2: POSITION MONITOR (FINAL, SANITY-PRESERVING VERSION)
# ============================================================

else:
    entry_exec = float(
        input("\nEnter your ENTRY VALUE (curve × $2000, full dollars): ")
    )

    pos_input = input("Position direction? [L/S]: ").strip().upper()
    direction = 1 if pos_input == "L" else -1
    side = "LONG FLATTENER" if direction == 1 else "SHORT STEEPENER"

    # --- Signal-space values (UNCHANGED, sacred) ---
    curve_now = today["curve"]
    z_now = today["z"]
    mu = today["ma_z"]
    sigma = today["std_z"]

    # --- Execution-space values (EXACTLY like backtest) ---
    curve_exec = (
            2 * today["ZN"]
            - 3 * today["ZT"]*2
    )*1000
    ZN = today["ZN"]
    ZT = today["ZT"]

    unreal_pnl = (
        curve_exec - entry_exec
        if direction == 1
        else entry_exec - curve_exec
    )

    # --- Z-distance to exits ---
    if direction == 1:  # LONG
        dz_tp = +0.0 - z_now
        dz_stop = -Z_STOP - z_now
    else:  # SHORT
        dz_tp = -1.0 - z_now
        dz_stop = +Z_STOP - z_now

    # --- Map signal move → execution move ---
    exec_per_signal = curve_exec / curve_now

    tp_exec = curve_exec + dz_tp * sigma * exec_per_signal
    stop_exec = curve_exec + dz_stop * sigma * exec_per_signal

    # ========================================================
    # OUTPUT (NOW IMPOSSIBLE TO MISINTERPRET)
    # ========================================================

    print("\n" + "=" * 60)
    print(" POSITION MONITOR (THIS TIME IT MEANS IT)")
    print("=" * 60)
    print(f"Position:            {side}")
    print(f"Date:                {df.index[-1].date()}")
    print("-" * 60)
    print(f"ZN:  {ZN:,.2f}     ZT:  {ZT:,.2f}")
    print(f"Current Z-Score:     {z_now:,.2f}")
    print("-" * 60)
    print(f"Entry Value ($):     {entry_exec:,.2f}")
    print(f"Current Value ($):   {curve_exec:,.2f}")
    print(f"Unrealized PnL ($):  {unreal_pnl:,.2f}")
    print("-" * 60)
    print(f"Take Profit ($):     {tp_exec:,.2f}  (Z target)")
    print(f"Stop Loss ($):       {stop_exec:,.2f} (|Z| = 2.2)")
    print("=" * 60)

