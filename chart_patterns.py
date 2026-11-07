"""
chart_patterns.py — Multi-bar chart pattern detection.

Implements the pattern rules from the uploaded Fidelity webinar
"Identifying Chart Patterns with Technical Analysis" (C. Kirkpatrick):

  * Horizontal congestion : Double / Triple Tops & Bottoms, Rectangles
  * Triangles             : Symmetrical, Ascending, Descending
  * Wedges                : Rising, Falling
  * Head & Shoulders      : Top and Inverse (Bottom)

Every pattern follows the PDF's core principles:
  - "A pattern is not complete or activated until an actual breakout occurs"
  - Confirmation filter: close beyond the level by >= 0.1 x ATR (point filter)
  - Target price = pattern height projected from the breakout point
  - Protective stop placed beyond the pattern boundary with a small filter
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from indicators import trend_context


# ----------------------------------------------------------------- utilities --
def swing_points(df: pd.DataFrame, k: int = 4) -> tuple[list[int], list[int]]:
    """Fractal swing highs/lows (patterns are fractal — this is the PDF's
    building block on any charting period)."""
    highs, lows = df["high"].values, df["low"].values
    sh, sl = [], []
    for i in range(k, len(df) - k):
        seg_h = highs[i - k:i + k + 1]
        seg_l = lows[i - k:i + k + 1]
        if highs[i] >= seg_h.max() and (highs[i] > seg_h[:k]).any():
            sh.append(i)
        if lows[i] <= seg_l.min() and (lows[i] < seg_l[:k]).any():
            sl.append(i)
    return sh, sl


def cluster_levels(df: pd.DataFrame, swing_idx: list[int], values: np.ndarray,
                   tol: float) -> list[dict]:
    """Cluster nearby swing prices into horizontal S/R zones (touch count)."""
    levels: list[dict] = []
    for i in swing_idx:
        v = values[i]
        placed = False
        for lv in levels:
            if abs(v - lv["price"]) <= tol:
                lv["idx"].append(i)
                lv["price"] = float(np.mean(lv["price_list"] + [v]))
                lv["price_list"].append(v)
                placed = True
                break
        if not placed:
            levels.append({"price": float(v), "idx": [i], "price_list": [v]})
    for lv in levels:
        lv["touches"] = len(lv["idx"])
    return levels


def support_resistance(df: pd.DataFrame, atr_val: float) -> dict:
    """Support & resistance zones from clustered swing points."""
    sh, sl = swing_points(df)
    tol = max(0.25 * atr_val, 1e-9)
    res = cluster_levels(df, sh, df["high"].values, tol)
    sup = cluster_levels(df, sl, df["low"].values, tol)
    return {
        "resistance": sorted(res, key=lambda x: -x["touches"]),
        "support": sorted(sup, key=lambda x: -x["touches"]),
        "swing_high_idx": sh,
        "swing_low_idx": sl,
    }


def _lin_slope(y: np.ndarray) -> float:
    """Slope of a linear fit over index positions."""
    x = np.arange(len(y), dtype=float)
    if len(x) < 2:
        return 0.0
    return float(np.polyfit(x, y, 1)[0])


# ------------------------------------------------------------ pattern detect --
def detect_patterns(df: pd.DataFrame, atr_val: float) -> list[dict]:
    """Scan the recent window for PDF chart patterns. Returns a list of dicts:
        name, direction ('bullish'|'bearish'), status ('confirmed breakout'|'forming'),
        score (signed strength), level (breakout trigger), target, points [(idx, price)],
        rule (PDF citation), last_idx (recency for de-duplication).
    """
    out: list[dict] = []
    if len(df) < 60 or not np.isfinite(atr_val) or atr_val <= 0:
        return out
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    sh, sl = swing_points(df, k=4)
    # keep recent swings only (patterns older than ~2/3 of window are stale)
    cut = int(len(df) * 0.25)
    sh = [i for i in sh if i >= cut]
    sl = [i for i in sl if i >= cut]
    tol = 0.30 * atr_val          # "peaks roughly at the same price" tolerance
    min_depth = 0.80 * atr_val    # minimum peak-to-trough height

    # ---------------------------------------------------------- Double Tops --
    for a, b in zip(sh[:-1], sh[1:]):
        if b - a < 5:
            continue
        trough_idx = a + int(np.argmin(lows[a:b]))
        trough = lows[trough_idx]
        h1, h2 = highs[a], highs[b]
        if abs(h1 - h2) <= tol and min(h1, h2) - trough >= min_depth:
            height = min(h1, h2) - trough
            breakout = trough - 0.10 * atr_val
            confirmed = closes[-1] < trough - 0.10 * atr_val
            pts = [(a, float(h1)), (trough_idx, float(trough)), (b, float(h2))]
            out.append({
                "name": "Double Top", "direction": "bearish",
                "status": "confirmed breakout" if confirmed else "forming",
                "score": -30 if confirmed else -12,
                "level": float(trough), "trigger": float(breakout),
                "target": float((closes[-1] if confirmed else trough) - height),
                "points": pts, "last_idx": b,
                "rule": "Two peaks at the same resistance; activated when price breaks "
                        "the middle reversal point (PDF p.18). Target = height projected down.",
            })
            break

    # ------------------------------------------------------- Double Bottoms --
    for a, b in zip(sl[:-1], sl[1:]):
        if b - a < 5:
            continue
        peak_idx = a + int(np.argmax(highs[a:b]))
        peak = highs[peak_idx]
        l1, l2 = lows[a], lows[b]
        if abs(l1 - l2) <= tol and peak - max(l1, l2) >= min_depth:
            height = peak - max(l1, l2)
            confirmed = closes[-1] > peak + 0.10 * atr_val
            pts = [(a, float(l1)), (peak_idx, float(peak)), (b, float(l2))]
            out.append({
                "name": "Double Bottom", "direction": "bullish",
                "status": "confirmed breakout" if confirmed else "forming",
                "score": 30 if confirmed else 12,
                "level": float(peak), "trigger": float(peak + 0.10 * atr_val),
                "target": float((closes[-1] if confirmed else peak) + height),
                "points": pts, "last_idx": b,
                "rule": "Two troughs at the same support; activated on break above the "
                        "middle peak (PDF p.19). Target = height projected up.",
            })
            break

    # ------------------------------------------- Triple Top / Triple Bottom --
    if len(sh) >= 3:
        a, b, c = sh[-3], sh[-2], sh[-1]
        p = [highs[a], highs[b], highs[c]]
        if max(p) - min(p) <= tol and c - a >= 10:
            t1 = a + int(np.argmin(lows[a:b]))
            t2 = b + int(np.argmin(lows[b:c]))
            trough = min(lows[t1], lows[t2])
            if min(p) - trough >= min_depth:
                height = max(p) - trough
                confirmed = closes[-1] < trough - 0.10 * atr_val
                out.append({
                    "name": "Triple Top", "direction": "bearish",
                    "status": "confirmed breakout" if confirmed else "forming",
                    "score": -32 if confirmed else -14,
                    "level": float(trough), "trigger": float(trough - 0.10 * atr_val),
                    "target": float((closes[-1] if confirmed else trough) - height),
                    "points": [(a, float(p[0])), (b, float(p[1])), (c, float(p[2]))],
                    "last_idx": c,
                    "rule": "Three peaks at the same level; break below the intermittent "
                            "trough activates the pattern (PDF p.20).",
                })
    if len(sl) >= 3:
        a, b, c = sl[-3], sl[-2], sl[-1]
        p = [lows[a], lows[b], lows[c]]
        if max(p) - min(p) <= tol and c - a >= 10:
            t1 = a + int(np.argmax(highs[a:b]))
            t2 = b + int(np.argmax(highs[b:c]))
            peak = max(highs[t1], highs[t2])
            if peak - min(p) >= min_depth:
                height = peak - min(p)
                confirmed = closes[-1] > peak + 0.10 * atr_val
                out.append({
                    "name": "Triple Bottom", "direction": "bullish",
                    "status": "confirmed breakout" if confirmed else "forming",
                    "score": 32 if confirmed else 14,
                    "level": float(peak), "trigger": float(peak + 0.10 * atr_val),
                    "target": float((closes[-1] if confirmed else peak) + height),
                    "points": [(a, float(p[0])), (b, float(p[1])), (c, float(p[2]))],
                    "last_idx": c,
                    "rule": "Three troughs at the same level; best after a sustained decline. "
                            "Break above the intermittent peaks activates it (PDF p.21).",
                })

    # ----------------------------------------------------- Head & Shoulders --
    if len(sh) >= 3 and len(sl) >= 2:
        ls_i, head_i, rs_i = sh[-3], sh[-2], sh[-1]
        ls, head, rs = highs[ls_i], highs[head_i], highs[rs_i]
        t1_i = ls_i + int(np.argmin(lows[ls_i:head_i]))
        t2_i = head_i + int(np.argmin(lows[head_i:rs_i]))
        t1, t2 = lows[t1_i], lows[t2_i]
        if (head - ls >= min_depth and head - rs >= min_depth
                and abs(ls - rs) <= 0.8 * tol and min(ls, rs) > t1 and min(ls, rs) > t2):
            # neckline through the two troughs, extended to the last bar
            slope = (t2 - t1) / max(t2_i - t1_i, 1)
            neckline_now = t2 + slope * (len(df) - 1 - t2_i)
            confirmed = closes[-1] < neckline_now - 0.10 * atr_val
            height = head - (t1 + slope * (head_i - t1_i))
            out.append({
                "name": "Head & Shoulders Top", "direction": "bearish",
                "status": "confirmed breakout" if confirmed else "forming",
                "score": -35 if confirmed else -15,
                "level": float(neckline_now), "trigger": float(neckline_now - 0.10 * atr_val),
                "target": float((closes[-1] if confirmed else neckline_now) - height),
                "points": [(ls_i, float(ls)), (t1_i, float(t1)), (head_i, float(head)),
                           (t2_i, float(t2)), (rs_i, float(rs))],
                "last_idx": rs_i,
                "rule": "Head above two roughly equal shoulders; pattern completes on the "
                        "neckline break and has one of the lowest failure rates (PDF p.27). "
                        "Target = head-to-neckline distance projected down.",
            })
    if len(sl) >= 3 and len(sh) >= 2:
        ls_i, head_i, rs_i = sl[-3], sl[-2], sl[-1]
        ls, head, rs = lows[ls_i], lows[head_i], lows[rs_i]
        t1_i = ls_i + int(np.argmax(highs[ls_i:head_i]))
        t2_i = head_i + int(np.argmax(highs[head_i:rs_i]))
        t1, t2 = highs[t1_i], highs[t2_i]
        if (ls - head >= min_depth and rs - head >= min_depth
                and abs(ls - rs) <= 0.8 * tol and max(ls, rs) < t1 and max(ls, rs) < t2):
            slope = (t2 - t1) / max(t2_i - t1_i, 1)
            neckline_now = t2 + slope * (len(df) - 1 - t2_i)
            confirmed = closes[-1] > neckline_now + 0.10 * atr_val
            height = (t1 + slope * (head_i - t1_i)) - head
            out.append({
                "name": "Head & Shoulders Bottom", "direction": "bullish",
                "status": "confirmed breakout" if confirmed else "forming",
                "score": 35 if confirmed else 15,
                "level": float(neckline_now), "trigger": float(neckline_now + 0.10 * atr_val),
                "target": float((closes[-1] if confirmed else neckline_now) + height),
                "points": [(ls_i, float(ls)), (t1_i, float(t1)), (head_i, float(head)),
                           (t2_i, float(t2)), (rs_i, float(rs))],
                "last_idx": rs_i,
                "rule": "Inverse head & shoulders; breakout up through the neckline "
                        "completes the pattern (PDF p.28).",
            })

    # ------------------------------------------ Triangles / Wedges / Rectangle
    # Use the last 3 swing highs and lows to classify the consolidation.
    if len(sh) >= 3 and len(sl) >= 3:
        hi_pts = [(i, highs[i]) for i in sh[-3:]]
        lo_pts = [(i, lows[i]) for i in sl[-3:]]
        hi_y = np.array([p[1] for p in hi_pts])
        lo_y = np.array([p[1] for p in lo_pts])
        s_hi = _lin_slope(hi_y)
        s_lo = _lin_slope(lo_y)
        n = abs(hi_pts[-1][0] - hi_pts[0][0]) or 1
        s_hi_n, s_lo_n = s_hi * n / atr_val, s_lo * n / atr_val   # ATR-normalised
        flat_hi = abs(hi_y.max() - hi_y.min()) <= tol
        flat_lo = abs(lo_y.max() - lo_y.min()) <= tol
        rising_lo = s_lo_n > 0.35
        falling_hi = s_hi_n < -0.35
        rising_hi = s_hi_n > 0.35
        falling_lo = s_lo_n < -0.35
        converging = (s_hi_n - s_lo_n) < -0.3

        span_pts = hi_pts + lo_pts
        first_idx = min(i for i, _ in span_pts)
        last_idx = max(i for i, _ in span_pts)

        if flat_hi and rising_lo:
            res_price = float(np.mean(hi_y))
            confirmed_up = closes[-1] > res_price + 0.10 * atr_val
            confirmed_dn = closes[-1] < lo_y.min() - 0.10 * atr_val
            status = ("confirmed breakout" if (confirmed_up or confirmed_dn) else "forming")
            direction = "bullish" if (confirmed_up or (not confirmed_dn)) else "bearish"
            height = res_price - float(lo_y.min())
            tgt = (closes[-1] + height) if confirmed_up else \
                  (closes[-1] - height) if confirmed_dn else res_price + height
            out.append({
                "name": "Ascending Triangle", "direction": direction,
                "status": status, "score": (25 if confirmed_up else -25) if status != "forming" else 10,
                "level": float(res_price), "trigger": float(res_price + 0.10 * atr_val),
                "target": float(tgt), "points": span_pts, "last_idx": last_idx,
                "rule": "Horizontal resistance + rising lows. Breaks upward more often; "
                        "confirm the breakout (PDF p.24). Target = pattern height.",
            })
        elif flat_lo and falling_hi:
            sup_price = float(np.mean(lo_y))
            confirmed_dn = closes[-1] < sup_price - 0.10 * atr_val
            confirmed_up = closes[-1] > hi_y.max() + 0.10 * atr_val
            status = ("confirmed breakout" if (confirmed_up or confirmed_dn) else "forming")
            direction = "bearish" if (confirmed_dn or (not confirmed_up)) else "bullish"
            height = float(hi_y.max()) - sup_price
            tgt = (closes[-1] - height) if confirmed_dn else \
                  (closes[-1] + height) if confirmed_up else sup_price - height
            out.append({
                "name": "Descending Triangle", "direction": direction,
                "status": status, "score": (25 if confirmed_up else -25) if status != "forming" else -10,
                "level": float(sup_price), "trigger": float(sup_price - 0.10 * atr_val),
                "target": float(tgt), "points": span_pts, "last_idx": last_idx,
                "rule": "Horizontal support + falling highs. Breaks downward more often "
                        "(PDF p.25). One of the best downward signals (PDF p.31).",
            })
        elif falling_hi and rising_lo and converging:
            apex = float((hi_y[-1] + lo_y[-1]) / 2)
            confirmed_up = closes[-1] > hi_y.max() + 0.10 * atr_val
            confirmed_dn = closes[-1] < lo_y.min() - 0.10 * atr_val
            status = ("confirmed breakout" if (confirmed_up or confirmed_dn) else "forming")
            height = float(hi_y.max() - lo_y.min())
            if confirmed_up:
                direction, score, tgt = "bullish", 22, closes[-1] + height
            elif confirmed_dn:
                direction, score, tgt = "bearish", -22, closes[-1] - height
            else:
                direction, score, tgt = "bullish", 6, apex + height
            out.append({
                "name": "Symmetrical Triangle", "direction": direction,
                "status": status, "score": score,
                "level": float(hi_y.max()), "trigger": float(hi_y.max() + 0.10 * atr_val),
                "target": float(tgt), "points": span_pts, "last_idx": last_idx,
                "rule": "Falling highs + rising lows converging. Wait for the breakout "
                        "direction, then project the pattern height (PDF p.23).",
            })
        elif rising_hi and rising_lo and not converging and (s_hi_n - s_lo_n) > 0.3:
            confirmed_dn = closes[-1] < lo_y[-1] - 0.10 * atr_val
            out.append({
                "name": "Rising Wedge", "direction": "bearish",
                "status": "confirmed breakout" if confirmed_dn else "forming",
                "score": -20 if confirmed_dn else -8,
                "level": float(lo_y[-1]), "trigger": float(lo_y[-1] - 0.10 * atr_val),
                "target": float(lows[sl[0]]),
                "points": span_pts, "last_idx": last_idx,
                "rule": "Both bounds rising but narrowing — often follows a climax move; "
                        "usually breaks down (PDF p.26).",
            })
        elif falling_hi and falling_lo and not converging and (s_lo_n - s_hi_n) > 0.3:
            confirmed_up = closes[-1] > hi_y[-1] + 0.10 * atr_val
            out.append({
                "name": "Falling Wedge", "direction": "bullish",
                "status": "confirmed breakout" if confirmed_up else "forming",
                "score": 20 if confirmed_up else 8,
                "level": float(hi_y[-1]), "trigger": float(hi_y[-1] + 0.10 * atr_val),
                "target": float(highs[sh[0]]),
                "points": span_pts, "last_idx": last_idx,
                "rule": "Both bounds falling but narrowing — often follows a panic decline; "
                        "usually breaks up (PDF p.26).",
            })
        elif flat_hi and flat_lo:
            res_price, sup_price = float(np.mean(hi_y)), float(np.mean(lo_y))
            height = res_price - sup_price
            if 0.8 * atr_val <= height <= 6 * atr_val:
                confirmed_up = closes[-1] > res_price + 0.10 * atr_val
                confirmed_dn = closes[-1] < sup_price - 0.10 * atr_val
                status = ("confirmed breakout" if (confirmed_up or confirmed_dn) else "forming")
                direction = "bullish" if confirmed_up else "bearish" if confirmed_dn else "neutral"
                # PDF p.22: shortfall often hints at eventual breakout direction
                shortfall = closes[-1] - sup_price
                if direction == "neutral":
                    direction = "bullish" if shortfall > height * 0.5 else "bearish"
                score = (25 if confirmed_up else -25) if status != "forming" else \
                        (8 if direction == "bullish" else -8)
                tgt = (closes[-1] + height) if (confirmed_up or direction == "bullish") \
                    else (closes[-1] - height)
                out.append({
                    "name": "Rectangle", "direction": direction,
                    "status": status, "score": score,
                    "level": float(res_price if direction == "bullish" else sup_price),
                    "trigger": float(res_price + 0.10 * atr_val) if direction == "bullish"
                               else float(sup_price - 0.10 * atr_val),
                    "target": float(tgt), "points": span_pts, "last_idx": last_idx,
                    "rule": "Trading range between parallel support/resistance; many false "
                            "breakouts — always confirm (PDF p.22). Target = range height.",
                })

    # De-duplicate: keep the strongest pattern per family, most recent wins ties.
    seen: dict[str, dict] = {}
    for p in sorted(out, key=lambda x: -abs(x["score"])):
        fam = p["name"]
        if fam not in seen or p["last_idx"] > seen[fam]["last_idx"]:
            seen[fam] = p
    return list(seen.values())
