"""
mtf.py — Multi-timeframe scanner.

Runs the FULL signal stack (indicators + chart patterns + candlesticks +
score + trade plan) on every timeframe for one pair, in parallel, and turns
the results into one advice table:

    Timeframe | Signal | Confidence | Entry | Stop loss | TP1 | TP2 | R:R | Pattern / bias

So the user gets, at a glance: "on 1 min → SELL (entry…, stop…, TP…)",
"on 1 hour → BUY (…)" etc., exactly the way the Fidelity PDF's rules are
applied per period (patterns are fractal, PDF p.5).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from data_feed import TIMEFRAMES, get_candles, pip_size
from indicators import add_indicators
from signals import analyze

# bars analysed per timeframe (enough for SMA50 + pattern windows, fast to fetch)
_TF_BARS = {"1 min": 350, "5 min": 350, "15 min": 350,
            "30 min": 350, "1 hour": 350, "1 day": 260}


# --------------------------------------------------------------- scanning ----
def analyze_one(pair: str, tf: str, source: str, token: str, env: str,
                count: int) -> tuple[str, str, dict]:
    df, used = get_candles(pair, tf, source, token, env, count)
    df = add_indicators(df)
    return tf, used, analyze(df)


def scan_all_timeframes(pair: str, source: str, token: str, env: str,
                        max_workers: int = 6) -> dict:
    """Run the analysis for all 6 timeframes in parallel.
    Returns {tf: ("tf", source_used, analysis_dict) or Exception}."""
    results: dict = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(analyze_one, pair, tf, source, token, env,
                          _TF_BARS[tf]): tf for tf in TIMEFRAMES}
        for fut in as_completed(futs):
            tf = futs[fut]
            try:
                results[tf] = fut.result()
            except Exception as e:              # keep the scan alive per-TF
                results[tf] = e
    return results


# ------------------------------------------------------------ table build ----
def build_mtf_table(pair: str, results: dict) -> pd.DataFrame:
    """Compact advice table: one row per timeframe."""
    pip = pip_size(pair)
    digits = 3 if pair.endswith("JPY") else 5
    fp = lambda v: f"{v:.{digits}f}"
    rows = []

    for tf in TIMEFRAMES:                                   # keep TF order
        r = results.get(tf)
        if r is None or isinstance(r, Exception):
            rows.append({"Timeframe": tf, "Signal": "—", "Conf %": np.nan,
                         "Entry": "data unavailable", "Stop loss": "—",
                         "Take profit 1": "—", "Take profit 2": "—",
                         "Risk:Reward": "—", "Pattern / bias": "—"})
            continue
        _, used, a = r
        sig, plan = a["signal"], a["plan"]
        verdict = sig["verdict"]
        if verdict == "BUY":
            signal = "🟢 BUY"
        elif verdict == "SELL":
            signal = "🔴 SELL"
        else:
            signal = "🟡 WAIT"

        if plan.get("direction") in ("long", "short"):
            entry = f"{fp(plan['entry_zone'][0])} – {fp(plan['entry_zone'][1])}"
            stop = fp(plan["stop"])
            tp1 = fp(plan["tp1"])
            tp2 = fp(plan["tp2"])
            rr = f"1 : {plan['rr1']:.1f}"
        else:   # WAIT → conditional stop-entry orders on both sides
            entry = (f"buy-stop ≥ {fp(plan['buy_trigger'])}  ·  "
                     f"sell-stop ≤ {fp(plan['sell_trigger'])}")
            stop = f"{fp(plan['buy_stop'])} / {fp(plan['sell_stop'])}"
            tp1 = f"{fp(plan['buy_tp'])} / {fp(plan['sell_tp'])}"
            tp2 = "—"
            rr = "—"

        pat = plan.get("pattern")
        if pat:
            note = f"{pat['name']} ({'breakout ✓' if pat['status'] == 'confirmed breakout' else 'forming…'})"
        else:
            note = a["context"]["structure"].title()

        rows.append({
            "Timeframe": tf,
            "Signal": signal,
            "Conf %": int(sig["confidence"]),
            "Entry": entry,
            "Stop loss": stop,
            "Take profit 1": tp1,
            "Take profit 2": tp2,
            "Risk:Reward": rr,
            "Pattern / bias": note,
        })
    return pd.DataFrame(rows)


def best_setup(table: pd.DataFrame) -> str:
    """Strongest directional (non-WAIT) row, for the highlight banner."""
    try:
        d = table[table["Signal"].isin(["🟢 BUY", "🔴 SELL"])].copy()
        if d.empty:
            return ("Every timeframe is in WAIT right now — no pattern is activated "
                    "yet. Per the PDF: let the breakout come to you; the conditional "
                    "entries in the table keep both sides covered.")
        d = d.sort_values("Conf %", ascending=False)
        b = d.iloc[0]
        side = "buy" if "BUY" in b["Signal"] else "sell"
        return (f"Strongest setup now: **{b['Timeframe']}** → {b['Signal']} "
                f"({int(b['Conf %'])}% confidence). {side.capitalize()} near "
                f"{b['Entry']}, stop {b['Stop loss']}, first target {b['Take profit 1']} "
                f"(R:R {b['Risk:Reward']}).")
    except Exception:
        return "Multi-timeframe summary temporarily unavailable."


def table_styler(table: pd.DataFrame):
    """Dark-theme colouring for the Signal / Confidence columns."""
    def paint_signal(v: str) -> str:
        if "BUY" in str(v):
            return "color:#26a69a;font-weight:800"
        if "SELL" in str(v):
            return "color:#ef5350;font-weight:800"
        if "WAIT" in str(v):
            return "color:#f0b90b;font-weight:800"
        return "color:#787b86"

    def paint_conf(v) -> str:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return ""
        if np.isnan(x):
            return ""
        color = "#26a69a" if x >= 60 else "#f0b90b" if x >= 45 else "#787b86"
        return f"color:{color};font-weight:700"

    # pandas >= 2.1 uses Styler.map; older versions use Styler.applymap
    try:
        st_ = table.style.map(paint_signal, subset=["Signal"])
    except AttributeError:
        st_ = table.style.applymap(paint_signal, subset=["Signal"])
    try:
        st_ = st_.map(paint_conf, subset=["Conf %"])
    except AttributeError:
        st_ = st_.applymap(paint_conf, subset=["Conf %"])
    try:
        st_ = st_.format({"Conf %": lambda v: "—" if pd.isna(v) else f"{int(v)}%"})
    except Exception:
        pass
    return st_
