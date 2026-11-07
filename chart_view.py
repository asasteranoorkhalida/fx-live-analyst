"""
chart_view.py — Plotly chart builder (TradingView dark style).
Pure-plotly module (no Streamlit calls) so it can be unit-tested headless.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_feed import TIMEFRAMES, price_digits


def fmt_price(v, digits: int) -> str:
    return f"{v:.{digits}f}" if v is not None and np.isfinite(v) else "—"


_TF_MINUTES = {"1 min": 1, "5 min": 5, "15 min": 15,
               "30 min": 30, "1 hour": 60, "1 day": 1440}


def merge_tick(df, tf: str, quote: dict | None):
    """Blend the freshest live quote into the displayed frame — investing.com
    behaviour: the newest candle visibly grows / shrinks (its close follows the
    tick, high/low expand) while the market is open, and a brand-new candle
    appears the moment a new time-bucket starts.

    The cached history keeps its indicator columns; the patched last row keeps
    them too, so SMA lines, RSI, patterns and S/R stay continuous. Never
    raises — on any problem the original frame is returned untouched."""
    try:
        if quote is None or df is None or len(df) == 0:
            return df
        price = float(quote.get("price") or 0)
        if not np.isfinite(price) or price <= 0:
            return df
        ts = pd.Timestamp(quote.get("ts") or pd.Timestamp.now(tz="UTC"))
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        ts = ts.tz_convert(df.index.tz)
        bucket = ts.floor(f"{_TF_MINUTES[tf]}min")
        df = df.copy()
        last = df.index[-1]
        i = len(df) - 1
        if bucket > last:
            # a new candle has started — seed it with the live price, but only
            # when the quote itself is fresh (< 24 h). A weekend-stale quote
            # must never fabricate a phantom candle days ahead.
            fresh = (pd.Timestamp.now(tz="UTC") - ts.tz_convert("UTC")) <= pd.Timedelta(hours=24)
            if fresh:
                row = {c: np.nan for c in df.columns}
                row.update({"open": price, "high": price, "low": price,
                            "close": price,
                            "volume": float(df["volume"].iloc[-1]) if "volume" in df.columns else 0.0})
                df = pd.concat([df, pd.DataFrame([row], index=pd.DatetimeIndex(
                    [bucket], name=df.index.name))])
        elif bucket == last:
            # same candle — make it breathe with the tick
            df.iloc[i, df.columns.get_loc("close")] = price
            df.iloc[i, df.columns.get_loc("high")] = max(float(df["high"].iloc[i]), price)
            df.iloc[i, df.columns.get_loc("low")] = min(float(df["low"].iloc[i]), price)
        # bucket < last → the stored candle is already newer; trust it
        return df
    except Exception:
        return df


def build_chart(df, pair, chart_type, sr, patterns, show_sr=True, show_labels=True,
                show_volume=True, show_rsi=True, zoom_range=None,
                uirevision=None) -> go.Figure:
    """zoom_range: optional (start_ts, end_ts) tuple for the x-axis view window.
    The full dataset stays available — the user can zoom back out with the
    mouse wheel, the mode-bar buttons or the range slider at the bottom.

    uirevision: when kept constant between live updates, plotly.js preserves
    the user's zoom / pan position across refreshes (investing.com behaviour:
    the chart ticks but your view never jumps). Pass a new value only when the
    view SHOULD reset (pair / timeframe / zoom-preset change)."""
    digits = price_digits(pair)
    n_rows = 1 + int(show_volume) + int(show_rsi)
    rh = {1: [1.0], 2: [0.80, 0.20], 3: [0.68, 0.15, 0.17]}[n_rows]
    specs = [[{"secondary_y": False}] for _ in range(n_rows)]
    fig = make_subplots(rows=n_rows, cols=1, shared_xaxes=True,
                        row_heights=rh, specs=specs, vertical_spacing=0.02)

    x = df.index
    # Plotly renders tz-aware data in UTC — strip tz so labels show MYT wall clock
    # (matches the session clock in the header).
    try:
        x = x.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    # --- main price panel ------------------------------------------------------
    if chart_type == "Candlestick":
        fig.add_trace(go.Candlestick(
            x=x, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            increasing_line_color="#26a69a", increasing_fillcolor="#26a69a",
            decreasing_line_color="#ef5350", decreasing_fillcolor="#ef5350",
            name=pair, line=dict(width=1.4)), row=1, col=1)
    else:
        fill = "tozeroy" if chart_type == "Area" else None
        fig.add_trace(go.Scatter(
            x=x, y=df["close"], mode="lines", name=pair,
            line=dict(color="#2962ff", width=2), fill=fill,
            fillcolor="rgba(41,98,255,0.14)"), row=1, col=1)

    if len(df) >= 20 and np.isfinite(df["sma20"].iloc[-1]):
        fig.add_trace(go.Scatter(x=x, y=df["sma20"], name="SMA 20",
                                 line=dict(color="#f0b90b", width=1.3)), row=1, col=1)
    if len(df) >= 50 and np.isfinite(df["sma50"].iloc[-1]):
        fig.add_trace(go.Scatter(x=x, y=df["sma50"], name="SMA 50",
                                 line=dict(color="#b39ddb", width=1.3)), row=1, col=1)

    # --- S/R lines --------------------------------------------------------------
    if show_sr:
        for lv in sr["resistance"][:3]:
            fig.add_hline(y=lv["price"], line=dict(color="rgba(239,83,80,.55)",
                          width=1.2, dash="dash"), row=1, col=1,
                          annotation_text=f"R {fmt_price(lv['price'], digits)}",
                          annotation_position="top right",
                          annotation_font=dict(color="#ef5350", size=10))
        for lv in sr["support"][:3]:
            fig.add_hline(y=lv["price"], line=dict(color="rgba(38,166,154,.55)",
                          width=1.2, dash="dash"), row=1, col=1,
                          annotation_text=f"S {fmt_price(lv['price'], digits)}",
                          annotation_position="bottom right",
                          annotation_font=dict(color="#26a69a", size=10))

    # --- pattern labels -----------------------------------------------------------
    if show_labels:
        for p in patterns[:4]:
            for idx, price in p["points"]:
                if 0 <= idx < len(df):
                    fig.add_trace(go.Scatter(
                        x=[x[idx]], y=[price], mode="markers",
                        marker=dict(size=7, symbol="circle",
                                    color="#26c6da" if p["direction"] == "bullish"
                                    else "#ff7043"),
                        showlegend=False,
                        hovertemplate=f"{p['name']}<extra></extra>"), row=1, col=1)
            if p["points"] and 0 <= p["points"][-1][0] < len(df):
                li, lp = p["points"][-1]
                fig.add_annotation(
                    x=x[li], y=lp,
                    text=f"{p['name']} ({'✓' if p['status'] == 'confirmed breakout' else '…'})",
                    showarrow=True, arrowhead=2, arrowsize=0.7, ax=18,
                    ay=-38 if p["direction"] == "bullish" else 38,
                    font=dict(size=10, color="#e3f2fd"),
                    bgcolor="rgba(30,34,45,.85)", bordercolor="#2a2e39", row=1, col=1)

    row = 2
    # --- volume --------------------------------------------------------------------
    if show_volume:
        vol = df["volume"].fillna(0)
        colors = ["#26a69a" if c >= o else "#ef5350"
                  for c, o in zip(df["close"], df["open"])]
        fig.add_trace(go.Bar(x=x, y=vol, marker_color=colors, name="Volume",
                             showlegend=False), row=row, col=1)
        fig.update_yaxes(title_text="Vol", row=row, col=1,
                         title_font=dict(size=10, color="#787b86"))
        row += 1

    # --- RSI -------------------------------------------------------------------------
    if show_rsi:
        fig.add_trace(go.Scatter(x=x, y=df["rsi14"], name="RSI 14",
                                 line=dict(color="#42a5f5", width=1.4),
                                 showlegend=False), row=row, col=1)
        fig.add_hline(y=70, line=dict(color="rgba(239,83,80,.5)", width=1, dash="dot"),
                      row=row, col=1)
        fig.add_hline(y=30, line=dict(color="rgba(38,166,154,.5)", width=1, dash="dot"),
                      row=row, col=1)
        fig.update_yaxes(range=[0, 100], row=row, col=1)
        fig.update_yaxes(title_text="RSI", row=row, col=1,
                         title_font=dict(size=10, color="#787b86"))

    # --- global layout -----------------------------------------------------------------
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#131722", plot_bgcolor="#131722",
        font=dict(color="#d1d4dc", family="Segoe UI, Arial"),
        height=810 if n_rows == 3 else (680 if n_rows == 2 else 520),
        margin=dict(l=8, r=88, t=34, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0,
                    bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified" if chart_type != "Candlestick" else "closest",
        xaxis_rangeslider_visible=False,
        dragmode="zoom",
    )
    # keep the user's zoom / pan across live re-renders -------------------------
    if uirevision:
        fig.update_layout(uirevision=uirevision)

    # --- live last-price tag (investing.com style) -----------------------------
    try:
        last_c = float(df["close"].iloc[-1])
        prev_c = float(df["close"].iloc[-2]) if len(df) > 1 else last_c
        lc = "#26a69a" if last_c >= prev_c else "#ef5350"
        fig.add_hline(y=last_c, row=1, col=1,
                      line=dict(color=lc, width=1.1, dash="dot"))
        fig.add_annotation(
            xref="paper", x=1.0, xanchor="left", yref="y", y=last_c,
            text=fmt_price(last_c, digits), showarrow=False,
            font=dict(color="#ffffff", size=11), bgcolor=lc,
            borderpad=3, yanchor="middle")
    except Exception:
        pass
    fig.update_xaxes(gridcolor="#1e222d", showgrid=True)
    fig.update_yaxes(gridcolor="#1e222d", showgrid=True,
                     tickformat=f",.{digits}f", row=1, col=1)
    # hide data voids dynamically: any gap well above the normal bar spacing
    # (weekend close, holidays) becomes a compressed rangebreak. Unlike fixed
    # "sat→mon" bounds this never hides real trading candles, whatever the
    # display timezone, and it adapts to every timeframe (1m … 1d).
    try:
        gaps = np.diff(x.values).astype("timedelta64[s]").astype(float)
        if len(gaps):
            med = float(np.median(gaps))
            thr = max(12 * 3600.0, 2.5 * med)
            big = np.where(gaps > thr)[0]
            if len(big):
                brk = [dict(bounds=[str(x[i]), str(x[i + 1])]) for i in big]
                fig.update_xaxes(rangebreaks=brk)
    except Exception:
        pass

    # --- zoom window (preset buttons in the app) ----------------------------
    if zoom_range is not None:
        try:
            start, end = zoom_range
            if hasattr(start, "tzinfo") and start.tzinfo is not None:
                start = start.tz_localize(None)
            if hasattr(end, "tzinfo") and end.tzinfo is not None:
                end = end.tz_localize(None)
            fig.update_xaxes(range=[start, end])
        except Exception:
            pass

    # --- TradingView-style range slider under the bottom panel --------------
    try:
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.045,
                                          bgcolor="#1e222d",
                                          bordercolor="#2a2e39"),
                         row=n_rows, col=1)
    except Exception:
        pass
    return fig
