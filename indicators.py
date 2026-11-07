"""
indicators.py — Classic technical indicators used by the signal engine.

All functions take/return a pandas DataFrame / Series and never mutate input.
RSI and ATR use Wilder's smoothing (standard on TradingView / MT4 / MT5).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(50.0)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([
        h - l,
        (h - prev_c).abs(),
        (l - prev_c).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with sma20, sma50, rsi14, atr14 columns added."""
    out = df.copy()
    out["sma20"] = sma(out["close"], 20)
    out["sma50"] = sma(out["close"], 50)
    out["rsi14"] = rsi(out["close"], 14)
    out["atr14"] = atr(out, 14)
    return out


def trend_context(df: pd.DataFrame) -> dict:
    """Higher-high / higher-low market structure from the last swing points."""
    k = 4
    highs, lows = df["high"], df["low"]
    swing_h, swing_l = [], []
    for i in range(k, len(df) - k):
        if highs.iloc[i] == highs.iloc[i - k:i + k + 1].max():
            swing_h.append(i)
        if lows.iloc[i] == lows.iloc[i - k:i + k + 1].min():
            swing_l.append(i)
    structure = "range"
    if len(swing_h) >= 2 and len(swing_l) >= 2:
        hh = highs.iloc[swing_h[-1]] > highs.iloc[swing_h[-2]]
        hl = lows.iloc[swing_l[-1]] > lows.iloc[swing_l[-2]]
        lh = highs.iloc[swing_h[-1]] < highs.iloc[swing_h[-2]]
        ll = lows.iloc[swing_l[-1]] < lows.iloc[swing_l[-2]]
        if hh and hl:
            structure = "uptrend"
        elif lh and ll:
            structure = "downtrend"
    return {
        "structure": structure,
        "last_swing_high": (swing_h[-1], float(highs.iloc[swing_h[-1]])) if swing_h else (None, np.nan),
        "last_swing_low": (swing_l[-1], float(lows.iloc[swing_l[-1]])) if swing_l else (None, np.nan),
        "swing_high_idx": swing_h,
        "swing_low_idx": swing_l,
    }
