"""
signals.py — Composite signal engine & trade-plan builder.

Combines trend structure, indicators, chart patterns and candlestick signals
into a single verdict (BUY / SELL / WAIT) with confidence, then builds the
trade plan exactly the way the uploaded Fidelity PDF teaches:

  * Breakout entry with confirmation filter (close beyond level by >= 0.1 ATR,
    ideally two consecutive closes — "multiple closes" filter, PDF p.10)
  * Entry stops beyond the breakout level (PDF p.11)
  * Protective stops beyond support/resistance / the breakout bar with a
    filter (PDF p.13)
  * Price targets = pattern height projected from the breakout (each pattern
    page of the PDF) or R-multiples when no pattern is present
  * Retracement (pullback/throwback) entry as the alternative entry (PDF p.15)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data_feed import pip_size
from indicators import trend_context, add_indicators
from chart_patterns import detect_patterns, support_resistance
from candle_patterns import detect_candle_patterns


# --------------------------------------------------------------- analysis ----
def analyze(df: pd.DataFrame) -> dict:
    """Run the full analysis stack over an OHLCV frame (indicators included)."""
    # defensive: guarantee the indicator columns exist (e.g. when a caller
    # passes a raw OHLCV frame, or a rate-limited feed produced a partial
    # frame somewhere upstream) — add_indicators is idempotent.
    if not {"sma20", "sma50", "rsi14", "atr14"}.issubset(df.columns):
        df = add_indicators(df)
    ctx = trend_context(df)
    atr_val = float(df["atr14"].iloc[-1])
    patterns = detect_patterns(df, atr_val)
    candles = detect_candle_patterns(df, atr_val)
    sr = support_resistance(df, atr_val)
    sig = build_signal(df, ctx, patterns, candles, sr, atr_val)
    plan = build_trade_plan(df, sig, patterns, sr, ctx, atr_val)
    sig["advice"] = build_advice(df, sig, plan, patterns, atr_val)
    return {
        "context": ctx,
        "atr": atr_val,
        "patterns": patterns,
        "candle_signals": candles,
        "sr": sr,
        "signal": sig,
        "plan": plan,
    }


# ----------------------------------------------------------- signal engine ---
def build_signal(df: pd.DataFrame, ctx: dict, patterns: list[dict],
                 candle_sigs: list[dict], sr: dict, atr_val: float) -> dict:
    score = 0
    reasons: list[tuple[str, int]] = []
    close = float(df["close"].iloc[-1])
    sma20 = float(df["sma20"].iloc[-1])
    sma50 = float(df["sma50"].iloc[-1])
    rsi_v = float(df["rsi14"].iloc[-1])
    warnings: list[str] = []

    # 1. Trend (max 30)
    if np.isfinite(sma50):
        if close > sma50:
            score += 8
            reasons.append(("Price above SMA50 (uptrend filter)", +8))
        else:
            score -= 8
            reasons.append(("Price below SMA50 (downtrend filter)", -8))
    if np.isfinite(sma20) and np.isfinite(sma50):
        if sma20 > sma50:
            score += 7
            reasons.append(("SMA20 above SMA50 (medium trend up)", +7))
        else:
            score -= 7
            reasons.append(("SMA20 below SMA50 (medium trend down)", -7))

    # 2. Market structure HH/HL vs LH/LL (max 15)
    struct = ctx["structure"]
    if struct == "uptrend":
        score += 15
        reasons.append(("Market structure: higher highs & higher lows", +15))
    elif struct == "downtrend":
        score -= 15
        reasons.append(("Market structure: lower highs & lower lows", -15))

    # 3. RSI momentum (max 10) + extreme warnings
    if rsi_v >= 70:
        warnings.append(f"RSI {rsi_v:.0f} — overbought; chasing longs here is risky "
                        "(wait for a pullback or reversal candle)")
    elif rsi_v <= 30:
        warnings.append(f"RSI {rsi_v:.0f} — oversold; be careful shorting here")
    if 55 <= rsi_v < 70:
        score += 10
        reasons.append((f"RSI {rsi_v:.0f} — bullish momentum", +10))
    elif 45 < rsi_v < 55:
        score += 0
    elif 30 < rsi_v <= 45:
        score -= 10
        reasons.append((f"RSI {rsi_v:.0f} — bearish momentum", -10))

    # 4. Chart patterns (max 40)
    pat_score = 0
    for p in patterns:
        if p["status"] == "confirmed breakout":
            pat_score += p["score"]
        else:
            pat_score += np.sign(p["score"]) * min(8, abs(p["score"]))
    pat_score = int(np.clip(pat_score, -40, 40))
    if pat_score != 0:
        score += pat_score
        drivers = [p["name"] for p in patterns if p["status"] == "confirmed breakout"]
        forming = [p["name"] for p in patterns if p["status"] == "forming"]
        if drivers:
            reasons.append((f"Pattern breakout: {', '.join(drivers)}", pat_score))
        elif forming:
            reasons.append((f"Pattern forming (not yet activated): {', '.join(forming)}", pat_score))

    # 5. Candlestick confirmations (max 15)
    cs_score = int(np.clip(sum(s["score"] for s in candle_sigs), -15, 15))
    if cs_score != 0:
        score += cs_score
        names = ", ".join(s["name"] for s in candle_sigs if s["score"] != 0)
        reasons.append((f"Candlestick signal: {names}", cs_score))

    # 6. Breakout confirmation filter (PDF p.10 — point + multiple closes)
    breakout = None
    levels = [l for l in sr["resistance"] + sr["support"]]
    for lv in levels:
        d = close - lv["price"]
        if abs(d) <= 0.12 * atr_val:
            breakout = {"side": "up" if d > 0 else "down", "level": float(lv["price"]),
                        "touches": lv["touches"]}
            break
    if breakout:
        need = 0.10 * atr_val
        prev_ok = (df["close"].iloc[-2] - breakout["level"]) * (1 if breakout["side"] == "up" else -1) > 0
        if breakout["side"] == "up":
            ok = close > breakout["level"] + need
            if ok and prev_ok:
                score += 12
                reasons.append((f"Breakout above {breakout['level']:.5f} confirmed by 2 closes "
                                f"(point filter ≥0.1 ATR)", +12))
            elif ok:
                score += 6
                reasons.append(("First close beyond resistance — one more close confirms", +6))
        else:
            ok = close < breakout["level"] - need
            if ok and prev_ok:
                score -= 12
                reasons.append((f"Breakdown below {breakout['level']:.5f} confirmed by 2 closes "
                                f"(point filter ≥0.1 ATR)", -12))
            elif ok:
                score -= 6
                reasons.append(("First close below support — one more close confirms", -6))

    score = int(np.clip(score, -100, 100))
    if score >= 20:
        verdict, conf = "BUY", min(96, 45 + abs(score) // 2)
    elif score <= -20:
        verdict, conf = "SELL", min(96, 45 + abs(score) // 2)
    else:
        verdict, conf = "WAIT", min(60, 30 + abs(score))
    return {
        "verdict": verdict, "confidence": conf, "score": score,
        "reasons": reasons, "warnings": warnings, "breakout": breakout,
        "rsi": rsi_v, "sma20": sma20, "sma50": sma50,
    }


# ------------------------------------------------------------ trade plan -----
def _nearest(levels: list[dict], price: float, above: bool) -> float | None:
    cands = [l["price"] for l in levels if (l["price"] > price) == above]
    if not cands:
        return None
    return float(min(cands, key=lambda x: abs(x - price)))


def build_trade_plan(df: pd.DataFrame, sig: dict, patterns: list[dict],
                     sr: dict, ctx: dict, atr_val: float) -> dict:
    close = float(df["close"].iloc[-1])
    verdict = sig["verdict"]
    direction = {"BUY": "long", "SELL": "short"}.get(verdict, "none")

    # --- key levels -----------------------------------------------------------
    swing_low = float(df["low"].iloc[-30:].min())
    swing_high = float(df["high"].iloc[-30:].max())
    sup_below = _nearest(sr["support"], close, above=False)
    res_above = _nearest(sr["resistance"], close, above=True)

    # pattern target / trigger (strongest pattern aligned with the verdict)
    pat = None
    if verdict != "WAIT":
        want = 1 if verdict == "BUY" else -1
        cands = [p for p in patterns if np.sign(p["score"]) == want]
        if cands:
            pat = max(cands, key=lambda p: abs(p["score"]))

    plan: dict = {"direction": direction, "pattern": pat, "close": close}

    if direction == "long":
        stop_ref = min(x for x in [sup_below, ctx["last_swing_low"][1], swing_low]
                       if x is not None and np.isfinite(x) and x < close)
        stop = stop_ref - 0.5 * atr_val                      # PDF p.13 filter
        entry_hi = close
        entry_lo = max(stop_ref, close - 0.5 * atr_val)      # pullback entry zone
        risk = entry_hi - stop
        r = lambda mult: entry_hi + mult * risk
        tp1 = res_above if (res_above and res_above >= entry_hi + 0.8 * risk) else r(1.5)
        tp2 = pat["target"] if (pat and pat.get("target") and pat["target"] > tp1) else r(2.5)
        if tp2 <= tp1:
            tp2 = tp1 + 1.0 * risk
    elif direction == "short":
        stop_ref = max(x for x in [res_above, ctx["last_swing_high"][1], swing_high]
                       if x is not None and np.isfinite(x) and x > close)
        stop = stop_ref + 0.5 * atr_val
        entry_lo = close
        entry_hi = min(stop_ref, close + 0.5 * atr_val)
        risk = stop - entry_lo
        r = lambda mult: entry_lo - mult * risk
        tp1 = sup_below if (sup_below and sup_below <= entry_lo - 0.8 * risk) else r(1.5)
        tp2 = pat["target"] if (pat and pat.get("target") and pat["target"] < tp1) else r(2.5)
        if tp2 >= tp1:
            tp2 = tp1 - 1.0 * risk
    else:
        # WAIT → conditional stop-entry orders on either side of the range (PDF p.11)
        buy_trig = res_above if res_above else swing_high
        sell_trig = sup_below if sup_below else swing_low
        plan.update({
            "buy_trigger": float(buy_trig + 0.10 * atr_val),
            "buy_stop": float(buy_trig - 1.2 * atr_val),
            "buy_tp": float(buy_trig + 2.0 * atr_val),
            "sell_trigger": float(sell_trig - 0.10 * atr_val),
            "sell_stop": float(sell_trig + 1.2 * atr_val),
            "sell_tp": float(sell_trig - 2.0 * atr_val),
        })
        return plan

    entry_mid = (entry_hi + entry_lo) / 2
    rr1 = abs(tp1 - entry_mid) / max(abs(entry_mid - stop), 1e-9)
    rr2 = abs(tp2 - entry_mid) / max(abs(entry_mid - stop), 1e-9)
    plan.update({
        "entry_zone": (float(entry_lo), float(entry_hi)),
        "entry_ideal": float(entry_mid),
        "stop": float(stop),
        "stop_ref": float(stop_ref),
        "tp1": float(tp1), "tp2": float(tp2),
        "rr1": float(rr1), "rr2": float(rr2),
        "risk_per_unit": float(abs(entry_mid - stop)),
        "pullback_ok": bool(pat and pat["status"] == "forming"),
    })
    return plan


# --------------------------------------------------------------- advice ------
def timeframe_advice(tf: str, sig: dict, atr_val: float, close: float,
                     sessions: dict) -> str:
    """Suggestion about the chosen timeframe, grounded in the PDF + FX practice."""
    base = {
        "1 min": ("1-minute chart = scalping. The PDF warns patterns generate MANY false "
                  "breakouts on the smallest periods, so always apply a confirmation "
                  "filter (two closes beyond the level) and expect noise. Trade only "
                  "during London/New York hours."),
        "5 min": ("5-minute chart = fast intraday. Patterns are fractal (they appear on "
                  "every period, PDF p.5) but signals need confirmation — use the point "
                  "filter (0.1 ATR) and avoid trading through news releases."),
        "15 min": ("15-minute chart = the sweet spot for intraday pattern trading: enough "
                   "bars per session for double tops/triangles to complete, with far fewer "
                   "false breakouts than 1m/5m."),
        "30 min": ("30-minute chart = calm intraday/swing-intraday. Good balance between "
                   "signal quality and number of setups per day."),
        "1 hour": ("1-hour chart = swing trading. Pattern breakouts here carry the day's "
                   "real flow; hold hours to a couple of days and let the pattern target "
                   "play out."),
        "1 day": ("Daily chart = position trading. Per the PDF, reversal patterns like "
                  "head & shoulders work best on higher periods — fewer signals but the "
                  "highest reliability. One candle = one full day, so stops must be wide."),
    }[tf]
    extra = ""
    if sessions.get("lon_ny_overlap"):
        extra = " London–New York overlap is ACTIVE right now — the best liquidity and cleanest patterns of the day."
    else:
        open_s = [k for k, v in sessions.get("sessions", {}).items() if v]
        extra = f" Active session(s): {', '.join(open_s) if open_s else 'none — market thin, spreads widen'}." \
                " Malaysian time: London opens 3pm, NY opens 8pm (MYT)."
    return base + extra


def build_advice(df: pd.DataFrame, sig: dict, plan: dict,
                 patterns: list[dict], atr_val: float) -> str:
    """One-paragraph conclusion & suggestion for the chosen pair + timeframe."""
    pair_tf = ""
    v = sig["verdict"]
    close = float(df["close"].iloc[-1])
    pips = lambda x: f"{x / pip_size(df.attrs.get('pair', 'EUR/USD')):.0f} pips" \
        if "pair" in df.attrs else f"{x:.5f}"

    if v == "BUY":
        head = f"Current bias: BUY ({sig['confidence']}% confidence)."
        body = (f"Best entry: {plan['entry_zone'][0]:.5f}–{plan['entry_zone'][1]:.5f} "
                f"(market now, or on a small pullback). Protective stop: {plan['stop']:.5f} "
                f"(beyond the last support/swing low with a 0.5×ATR filter, per the PDF). "
                f"Take profit 1 at {plan['tp1']:.5f} ({plan['rr1']:.1f}R), "
                f"take profit 2 at {plan['tp2']:.5f} ({plan['rr2']:.1f}R).")
    elif v == "SELL":
        head = f"Current bias: SELL ({sig['confidence']}% confidence)."
        body = (f"Best entry: {plan['entry_zone'][0]:.5f}–{plan['entry_zone'][1]:.5f} "
                f"(market now, or on a small throwback up). Protective stop: {plan['stop']:.5f} "
                f"(beyond the last resistance/swing high with a 0.5×ATR filter). "
                f"Take profit 1 at {plan['tp1']:.5f} ({plan['rr1']:.1f}R), "
                f"take profit 2 at {plan['tp2']:.5f} ({plan['rr2']:.1f}R).")
    else:
        head = f"Current bias: WAIT ({sig['confidence']}% confidence) — no activated pattern or clean trend yet."
        body = (f"Conditional plan: buy-stop entry above {plan['buy_trigger']:.5f} "
                f"(stop {plan['buy_stop']:.5f}, target {plan['buy_tp']:.5f}) or sell-stop "
                f"entry below {plan['sell_trigger']:.5f} (stop {plan['sell_stop']:.5f}, "
                f"target {plan['sell_tp']:.5f}). The PDF's rule: a pattern is only "
                "activated once an actual breakout occurs — let price prove it.")

    if plan.get("pattern"):
        p = plan["pattern"]
        body += f" Key pattern driving the plan: {p['name']} ({p['status']})."
    body += " Always risk only 1–2% of the account per trade and honour the protective stop."
    return head + " " + body
