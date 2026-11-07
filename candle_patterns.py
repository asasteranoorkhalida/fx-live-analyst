"""
candle_patterns.py — Single & two-bar candlestick pattern detection.

Implements the candlestick section of the uploaded Fidelity PDF (pp. 33-38):
Doji, Harami, Hammer / Hanging Man, Shooting Star / Inverted Hammer,
Bullish & Bearish Engulfing, Piercing Line / Dark Cloud Cover.

The PDF's key warning is respected: candlesticks are REVERSAL patterns —
they only matter after a meaningful move ("upward reversal patterns after a
correction in a longer upward trend show the best performance"), and nothing
is acted upon until the pattern is confirmed by a break in its direction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _trend_before(df: pd.DataFrame, i: int, lookback: int = 10) -> str:
    """Direction of the move that led into candle i ('up' | 'down' | 'flat')."""
    a = max(0, i - lookback)
    if i - a < 4:
        return "flat"
    move = df["close"].iloc[i] - df["close"].iloc[a]
    ref = 0.35 * df["atr14"].iloc[i] if np.isfinite(df["atr14"].iloc[i]) else 1e-9
    if move > ref:
        return "up"
    if move < -ref:
        return "down"
    return "flat"


def detect_candle_patterns(df: pd.DataFrame, atr_val: float) -> list[dict]:
    """Check the last 3 candles for PDF candlestick patterns.
    Returns dicts: name, direction ('bullish'|'bearish'|'neutral'),
    score (signed), bar_idx, rule (PDF citation)."""
    out: list[dict] = []
    n = len(df)
    if n < 25 or not np.isfinite(atr_val) or atr_val <= 0:
        return out

    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    start = max(n - 3, 20)
    for i in range(start, n):
        body = abs(c[i] - o[i])
        rng = h[i] - l[i]
        if rng <= 0.20 * atr_val:          # dead candle — skip
            continue
        upper = h[i] - max(c[i], o[i])
        lower = min(c[i], o[i]) - l[i]
        bull = c[i] > o[i]
        prev_body = abs(c[i - 1] - o[i - 1])
        prev_bull = c[i - 1] > o[i - 1]
        trend = _trend_before(df, i)

        # ------------------------------------------------------------- Doji --
        if body <= 0.10 * rng and rng >= 0.6 * atr_val:
            out.append({
                "name": "Doji", "direction": "neutral", "score": 0, "bar_idx": i,
                "rule": "Open ≈ close: market indecision, a possible warning of a "
                        "price change (PDF p.33).",
            })

        # ------------------------------------- Hammer / Hanging Man (shape) --
        if body > 0 and lower >= 2.0 * body and upper <= 0.6 * body and body <= 0.35 * rng:
            if trend == "down":
                out.append({
                    "name": "Hammer", "direction": "bullish", "score": 8, "bar_idx": i,
                    "rule": "Long lower shadow after a decline — buying appeared at the "
                            "lows. Confirm with a break above the hammer's high (PDF p.35).",
                })
            elif trend == "up":
                out.append({
                    "name": "Hanging Man", "direction": "bearish", "score": -5, "bar_idx": i,
                    "rule": "Same shape after an advance. The PDF notes it breaks either "
                            "way with below-average performance — treat as a warning only (p.35).",
                })

        # ------------------------- Shooting Star / Inverted Hammer (shape) --
        if body > 0 and upper >= 2.0 * body and lower <= 0.6 * body and body <= 0.35 * rng:
            if trend == "up":
                out.append({
                    "name": "Shooting Star", "direction": "bearish", "score": -8, "bar_idx": i,
                    "rule": "Long upper shadow after an advance — sellers rejected the "
                            "highs. Average performance; wait for confirmation (PDF p.36).",
                })
            elif trend == "down":
                out.append({
                    "name": "Inverted Hammer", "direction": "bullish", "score": 5, "bar_idx": i,
                    "rule": "Inverted hammer after a decline — possible upward reversal, "
                            "needs a confirming close higher (PDF p.36).",
                })

        # -------------------------------------------------------- Engulfing --
        if prev_body >= 0.25 * atr_val and body > prev_body * 1.05:
            if (not prev_bull) and bull and min(o[i - 1], c[i - 1]) <= o[i] \
                    and max(o[i - 1], c[i - 1]) >= c[i] and trend == "down":
                out.append({
                    "name": "Bullish Engulfing", "direction": "bullish", "score": 10, "bar_idx": i,
                    "rule": "Tall white body engulfs the prior black body after a decline — "
                            "very good performance in a downtrend (PDF p.37).",
                })
            elif prev_bull and (not bull) and min(o[i - 1], c[i - 1]) <= o[i] \
                    and max(o[i - 1], c[i - 1]) >= c[i] and trend == "up":
                out.append({
                    "name": "Bearish Engulfing", "direction": "bearish", "score": -10, "bar_idx": i,
                    "rule": "Tall black body engulfs the prior white body after an advance — "
                            "classic topping reversal (PDF p.37).",
                })

        # ----------------------------------------------------------- Harami --
        if prev_body >= 0.6 * atr_val and body <= 0.45 * prev_body:
            inside = min(o[i], c[i]) >= min(o[i - 1], c[i - 1]) - 1e-12 and \
                     max(o[i], c[i]) <= max(o[i - 1], c[i - 1]) + 1e-12
            if inside and bull != prev_bull:
                out.append({
                    "name": "Harami", "direction": "neutral", "score": 0, "bar_idx": i,
                    "rule": "Small 'spinning top' inside the prior body — tension can "
                            "break either way; do not assume reversal (PDF p.34).",
                })

        # ------------------------------ Piercing Line / Dark Cloud Cover ----
    # two-bar patterns evaluated on the final closed bar
    i = n - 1
    body, prev_body = abs(c[i] - o[i]), abs(c[i - 1] - o[i - 1])
    prev_bull = c[i - 1] > o[i - 1]
    prev_mid = (o[i - 1] + c[i - 1]) / 2
    trend = _trend_before(df, i - 1)

    if (not prev_bull) and c[i] > o[i] and prev_body >= 0.4 * atr_val \
            and o[i] <= c[i - 1] and prev_mid < c[i] < o[i - 1] and trend == "down":
        out.append({
            "name": "Piercing Line", "direction": "bullish", "score": 9, "bar_idx": i,
            "rule": "White candle closes above the midpoint of the prior black body "
                    "after a decline — upward reversal (PDF p.38).",
        })
    if prev_bull and c[i] < o[i] and prev_body >= 0.4 * atr_val \
            and o[i] >= c[i - 1] and o[i - 1] > c[i] > prev_mid and trend == "up":
        out.append({
            "name": "Dark Cloud Cover", "direction": "bearish", "score": -9, "bar_idx": i,
            "rule": "Black candle closes below the midpoint of the prior white body "
                    "after an advance — downward reversal (PDF p.38).",
        })

    # keep the strongest signal per name, drop duplicates on the same bar
    seen: dict[tuple, dict] = {}
    for p in sorted(out, key=lambda x: -abs(x["score"])):
        key = (p["name"], p["bar_idx"])
        if key not in seen:
            seen[key] = p
    return sorted(seen.values(), key=lambda x: x["bar_idx"])
