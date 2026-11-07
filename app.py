"""
app.py — FX Live Analyst: live forex charts + PDF-based pattern signal engine.

The page feels like a real trading terminal (investing.com style):
  * the price strip, chart, verdict and trade plan live in st.fragment blocks
    that re-run on a timer (3 s / 5 s / 10 s / 30 s) — the last candle moves
    up and down on its own while the market is open;
  * the user's zoom / pan position is preserved between ticks (plotly
    uirevision), so the chart ticks without ever jumping around;
  * the multi-timeframe advice table and the watchlist rescan every 60 s.

Run:  streamlit run app.py
"""
from __future__ import annotations

import time
import warnings

import numpy as np
import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore")

from data_feed import (ALL_PAIRS, PAIR_GROUPS, TIMEFRAMES, WATCHLIST,
                       get_candles, get_live_quote, pip_size, price_digits,
                       trading_sessions)
from indicators import add_indicators
from chart_patterns import support_resistance
from signals import analyze, timeframe_advice
from chart_view import build_chart, fmt_price, merge_tick
from mtf import scan_all_timeframes, build_mtf_table, best_setup, table_styler

# ----------------------------------------------------------------- page init --
st.set_page_config(
    page_title="FX Live Analyst — Live Forex Signals & Chart Patterns",
    page_icon="static/icon-192.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# TradingView-style dark theme -------------------------------------------------
st.markdown("""
<style>
    .stApp { background:#131722; color:#d1d4dc; }
    section[data-testid="stSidebar"] { background:#1e222d; border-right:1px solid #2a2e39; }
    .block-container { padding-top:1.1rem; padding-bottom:2rem; max-width:1500px; }
    h1,h2,h3,h4 { color:#f0f3fa !important; }
    span,p,div,label,li { color:#d1d4dc; }
    .badge { display:inline-block; padding:.28em .85em; border-radius:.45rem;
             font-weight:800; letter-spacing:.06em; font-size:1.15rem; }
    .badge-buy  { background:rgba(38,166,154,.16); color:#26a69a; border:1.5px solid #26a69a; }
    .badge-sell { background:rgba(239,83,80,.16);  color:#ef5350; border:1.5px solid #ef5350; }
    .badge-wait { background:rgba(255,193,7,.12);  color:#f0b90b; border:1.5px solid #f0b90b; }
    .chip { display:inline-block; padding:.16em .6em; margin:.12em .18em; border-radius:1rem;
            font-size:.78rem; border:1px solid #2a2e39; background:#1e222d; color:#9aa3b5; }
    .chip-on { color:#26a69a; border-color:#26a69a; background:rgba(38,166,154,.08); }
    .price-big { font-size:2.15rem; font-weight:800; line-height:1.05; }
    .pair-big  { font-size:1.5rem;  font-weight:800; color:#f0f3fa; }
    .up   { color:#26a69a !important; }
    .down { color:#ef5350 !important; }
    .muted{ color:#787b86 !important; }
    div[data-testid="stDataFrame"] { border:1px solid #2a2e39; border-radius:.5rem; }
    hr { border-color:#2a2e39; }
    .footer-note { color:#787b86; font-size:.82rem; }
    .brand { display:flex; align-items:center; gap:.5rem; margin:0 0 .3rem 0; flex-wrap:wrap; }
    .brand-name { font-size:1.28rem; font-weight:900; letter-spacing:.07em; color:#f0f3fa; }
    .brand-name span { color:#26a69a; }
    .live-dot { width:9px; height:9px; border-radius:50%; background:#26a69a;
                display:inline-block; margin-right:.3rem; animation:fxpulse 1.6s infinite; }
    @keyframes fxpulse {
      0%   { box-shadow:0 0 0 0 rgba(38,166,154,.55); }
      70%  { box-shadow:0 0 0 8px rgba(38,166,154,0); }
      100% { box-shadow:0 0 0 0 rgba(38,166,154,0); } }
    .zoom-hint { color:#787b86; font-size:.8rem; text-align:right; padding-top:.75rem; }
    .tick-up   { animation:tickflashup .9s ease-out; }
    .tick-down { animation:tickflashdown .9s ease-out; }
    @keyframes tickflashup {
      0%   { text-shadow:0 0 18px rgba(38,166,154,.95); }
      100% { text-shadow:none; } }
    @keyframes tickflashdown {
      0%   { text-shadow:0 0 18px rgba(239,83,80,.95); }
      100% { text-shadow:none; } }
</style>
""", unsafe_allow_html=True)

# PWA / mobile-install metadata (files served from ./static — see README "Play Store")
# Streamlit moved the user-static route to /app/static in newer versions — detect it.
try:
    from streamlit.url_util import STATIC_SERVING_ENDPOINT as _SSE
    STATIC_BASE = _SSE.strip("/")            # e.g. "app/static" (Streamlit ≥ 1.4x)
except Exception:
    STATIC_BASE = "static"                    # older versions served ./static directly

st.markdown(
    f"<link rel='manifest' href='{STATIC_BASE}/manifest.json'>"
    "<meta name='theme-color' content='#131722'>"
    f"<link rel='apple-touch-icon' href='{STATIC_BASE}/icon-192.png'>"
    "<meta name='mobile-web-app-capable' content='yes'>"
    "<meta name='apple-mobile-web-app-capable' content='yes'>"
    "<meta name='apple-mobile-web-app-title' content='FX Analyst'>"
    "<meta name='apple-mobile-web-app-status-bar-style' content='black-translucent'>",
    unsafe_allow_html=True)


# ----------------------------------------------------------------- helpers ----
@st.cache_data(show_spinner=False)
def _fetch(pair, tf, source, token, env, count, bucket):
    df, used = get_candles(pair, tf, source, token, env, count)
    return df, used


def fetch_cached(pair, tf, source, token, env, count, ttl):
    bucket = int(time.time() // max(ttl, 3))
    return _fetch(pair, tf, source, token, env, count, bucket)


@st.cache_data(show_spinner=False)
def _watch(wl_tuple, tf, bucket):
    rows = []
    for p in wl_tuple:
        try:
            df, _ = get_candles(p, tf, "Yahoo Finance", "", "Practice (demo)", 80)
            df = add_indicators(df)
            last, prev = df["close"].iloc[-1], df["close"].iloc[-2]
            rsi_v = float(df["rsi14"].iloc[-1])
            above = last > float(df["sma20"].iloc[-1]) if np.isfinite(df["sma20"].iloc[-1]) else True
            bias = "▲ Buy bias" if (rsi_v >= 55 and above) else \
                   "▼ Sell bias" if (rsi_v <= 45 and not above) else "● Neutral"
            rows.append({"Pair": p, "Price": float(last),
                         "Δ %": (last / prev - 1) * 100 if prev else 0.0,
                         "RSI": rsi_v, "Bias": bias})
        except Exception:
            rows.append({"Pair": p, "Price": np.nan, "Δ %": np.nan,
                         "RSI": np.nan, "Bias": "—"})
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def _mtf_scan(pair_, source_, token_, env_, bucket_):
    return scan_all_timeframes(pair_, source_, token_, env_)


# zoom presets per timeframe: label -> hours shown back from the latest bar
# ("ALL" = the whole loaded history; user can still wheel-zoom freely)
ZOOM_PRESETS = {
    "1 min":  [("1H", 1), ("4H", 4), ("8H", 8), ("ALL", None)],
    "5 min":  [("6H", 6), ("12H", 12), ("1D", 24), ("ALL", None)],
    "15 min": [("12H", 12), ("1D", 24), ("2D", 48), ("ALL", None)],
    "30 min": [("1D", 24), ("2D", 48), ("4D", 96), ("ALL", None)],
    "1 hour": [("1D", 24), ("3D", 72), ("1W", 168), ("ALL", None)],
    "1 day":  [("1M", 720), ("3M", 2160), ("6M", 4320), ("ALL", None)],
}


# ================================================================== SIDEBAR ===
with st.sidebar:
    st.markdown("### ⚙️ Settings")

    pair = st.selectbox("Currency pair", ALL_PAIRS, index=ALL_PAIRS.index("EUR/USD"),
                        help="Majors first, then crosses. OANDA notation is used automatically.")
    grp = "Majors" if pair in PAIR_GROUPS["Majors"] else "Crosses"
    st.caption(f"Group: **{grp}**  ·  1 of {len(ALL_PAIRS)} pairs supported")

    tf = st.radio("Timeframe", list(TIMEFRAMES.keys()), index=2, horizontal=True)

    chart_type = st.selectbox("Chart type", ["Candlestick", "Line", "Area"], index=0)

    n_bars = st.slider("Candles to analyse", 150, 800, 400, step=50)

    st.divider()
    st.markdown("#### 🔌 Data source")
    source = st.radio("Feed", ["OANDA v20", "Yahoo Finance (free)"], index=1,
                      help="OANDA gives broker-grade live rates + tick volume. "
                           "Yahoo needs no key and is the default for beginners.")
    token, env = "", "Practice (demo)"
    if source == "OANDA v20":
        token = st.text_input("OANDA API token", type="password",
                              help="Generate at oanda.com → My Account → Manage API Access "
                                   "(use a practice account first!). Leave empty to auto-fall "
                                   "back to Yahoo Finance.")
        env = st.radio("OANDA environment", list(["Practice (demo)", "Live (real)"]),
                       index=0, horizontal=True)

    st.divider()
    st.markdown("#### 🔴 Live 24h feed")
    live_every = st.select_slider("Chart ticks every",
                                  options=["1 s", "2 s", "3 s", "5 s", "10 s", "30 s", "Off"],
                                  value="2 s",
                                  help="How often the price strip and the newest candle "
                                       "refresh themselves — no clicking needed, like "
                                       "investing.com. Turbo (1–2 s) gives constant "
                                       "visible movement.")
    st.caption("The chart ticks automatically 24h while this tab is open and your "
               "zoom / pan position is kept between ticks. Free Yahoo quotes move "
               "every few seconds; add an OANDA token for true streaming rates. "
               "The FX market itself rests on weekends (Sat ~05:00 → Mon ~05:00 MYT).")
    st.button("🔄 Refresh now", use_container_width=True,
              help="Reload the whole page (chart, signals, tables) immediately.")

    st.divider()
    with st.expander("💰 Position sizing (optional)"):
        balance = st.number_input("Account balance (USD)", 100.0, 10_000_000.0, 10_000.0, 500.0)
        risk_pct = st.slider("Risk per trade (%)", 0.25, 5.0, 1.0, 0.25)

    with st.expander("📐 Methodology (Fidelity PDF)"):
        st.markdown(
            "Signals follow **Identifying Chart Patterns with Technical Analysis** "
            "(Fidelity / C. Kirkpatrick):\n\n"
            "- Patterns = **Double/Triple Tops & Bottoms, Rectangles, Symmetrical / "
            "Ascending / Descending Triangles, Wedges, Head & Shoulders**\n"
            "- Candlesticks: **Doji, Harami, Hammer/Hanging Man, Shooting Star / "
            "Inverted Hammer, Engulfing, Piercing / Dark Cloud**\n"
            "- A pattern is only *activated* by an actual **breakout** (confirmation "
            "filter: close beyond level by ≥ 0.1×ATR, two closes preferred)\n"
            "- **Entry stops** beyond the breakout level, **protective stops** beyond "
            "support/resistance + filter, targets = **pattern height projected** from "
            "the breakout, pullback/throwback entries noted")
    st.caption("⚠️ Educational tool — not financial advice.")


# live tick interval for the fragments (None = plain call, no timer)
LIVE_SECS = {"1 s": 1, "2 s": 2, "3 s": 3, "5 s": 5, "10 s": 10, "30 s": 30}
secs = LIVE_SECS.get(live_every)          # None when "Off"


# ================================================================= LIVE CORE ==
# One cached analysis per TTL bucket: the chart zone and the plan zone both pull
# from it, so every section of the page always shows the exact same numbers.

@st.cache_data(show_spinner=False)
def _live_analysis(pair_, tf_, source_, token_, env_, n_bars_, bucket_):
    df_, used_ = get_candles(pair_, tf_, source_, token_, env_, n_bars_)
    df_ = add_indicators(df_)
    return df_, used_, analyze(df_)


@st.cache_data(show_spinner=False)
def _quote(pair_, token_, env_, bucket_):
    """1-second bucket → every live tick pulls a genuinely fresh quote.
    OANDA token → real-time bid/ask; otherwise Yahoo's light chart API.
    Returns None when throttled — the chart then simply holds its last state."""
    return get_live_quote(pair_, token_, env_)


def _live_bucket():
    """TTL bucket: 4 s while the live feed is on (near-tick), feed defaults when off."""
    ttl = 4 if secs else TIMEFRAMES[tf][2]
    return int(time.time() // max(ttl, 3))


def _frag(run_every, fn):
    """st.fragment when available (Streamlit ≥ 1.37); plain call otherwise."""
    if run_every is not None and hasattr(st, "fragment"):
        return st.fragment(run_every=run_every)(fn)
    return fn


# ========================================================== CHART ZONE (live) ==
def _chart_zone():
    sess = trading_sessions()
    try:
        df, source_used, analysis = _live_analysis(pair, tf, source, token, env,
                                                   n_bars, _live_bucket())
    except Exception as e:
        st.error(f"**Could not load data for {pair} ({tf}).**\n\n{e}")
        st.info("Check your internet connection / OANDA token, or switch the feed "
                "to Yahoo Finance (free) in the sidebar.")
        return

    sig, plan = analysis["signal"], analysis["plan"]

    # --- freshest tick: the newest candle breathes with every refresh -------
    quote = _quote(pair, token, env, int(time.time()))
    df_disp = merge_tick(df, tf, quote)

    last_c = float(df_disp["close"].iloc[-1])
    prev_c = float(df_disp["close"].iloc[-2]) if len(df_disp) > 1 else last_c
    if quote and quote.get("price"):
        last_c = float(quote["price"])              # the strip follows the tick
        pc = float(quote.get("prev_close") or 0)
        if 0.5 < pc < last_c * 1.2:                 # sane previous-session close
            prev_c = pc
    chg = last_c - prev_c
    chg_pct = chg / prev_c * 100 if prev_c else 0.0
    digits = price_digits(pair)
    atr_pips = analysis["atr"] / pip_size(pair)
    up = chg >= 0

    # tick flash — compare against the price shown on the previous refresh
    disp_key = f"disp_{pair}_{tf}"
    prev_disp = st.session_state.get(disp_key)
    tick = 0 if prev_disp is None else (1 if last_c > prev_disp else
                                        (-1 if last_c < prev_disp else 0))
    st.session_state[disp_key] = last_c
    flash = "tick-up" if tick > 0 else "tick-down" if tick < 0 else ""
    tick_ic = "▲" if tick > 0 else "▼" if tick < 0 else "●"

    head_l, head_r = st.columns([3, 2])
    with head_l:
        st.markdown(
            f"<span class='pair-big'>{pair}</span> &nbsp;"
            f"<span class='chip'>{tf}</span>"
            f"<span class='chip'>{source_used}</span><br>"
            f"<span class='price-big {'up' if up else 'down'} {flash}'>"
            f"{fmt_price(last_c, digits)}</span> "
            f"<span class='{ 'up' if up else 'down'}' style='font-size:1.05rem'>"
            f"{'▲' if up else '▼'} {chg:+.{digits}f} ({chg_pct:+.2f}%)</span> "
            f"<span class='chip'>{tick_ic} tick · {sess['myt'].strftime('%H:%M:%S')} MYT</span>",
            unsafe_allow_html=True)
    with head_r:
        chips = []
        wd_, hh_ = sess["myt"].weekday(), sess["myt"].hour
        if (wd_ == 5 and hh_ >= 5) or wd_ == 6:   # Sat ≥05:00 MYT → Sun (Fri 5pm ET close)
            chips.append("<span class='chip' style='color:#ef5350;border-color:#ef5350'>"
                         "🔴 Market closed — weekend</span>")
        if quote and quote.get("bid") is not None:
            chips.append(f"<span class='chip'>bid {quote['bid']:.{digits}f} · "
                         f"ask {quote['ask']:.{digits}f}</span>")
        try:
            if quote is not None and quote.get("ts") is not None:
                age = pd.Timestamp.now(tz="Asia/Kuala_Lumpur") - pd.Timestamp(quote["ts"])
                if age > pd.Timedelta(minutes=6):
                    chips.append("<span class='chip' style='color:#f0b90b;border-color:#f0b90b'>"
                                 "⏸ quotes paused (market closed?)</span>")
        except Exception:
            pass
        for name, on in sess["sessions"].items():
            chips.append(f"<span class='chip {'chip-on' if on else ''}'>{'🟢' if on else '⚪'} {name}</span>")
        if sess["lon_ny_overlap"]:
            chips.append("<span class='chip chip-on'>🔥 LDN–NY overlap</span>")
        st.markdown("<div style='text-align:right'>" + "".join(chips) + "</div>",
                    unsafe_allow_html=True)

    # friendly explanation when the real market is resting (investing.com does
    # the same — FX simply has no ticks from Fri 5pm ET to Sun 5pm ET)
    try:
        if quote is not None and quote.get("ts") is not None:
            qage = pd.Timestamp.now(tz="Asia/Kuala_Lumpur") - pd.Timestamp(quote["ts"])
            if qage > pd.Timedelta(minutes=10):
                st.info(f"😴 **The FX market is resting** — last quote arrived "
                        f"{pd.Timestamp(quote['ts']).strftime('%a %H:%M')} MYT "
                        f"({qage.components.hours} h ago). Charts freeze at Friday's close, "
                        f"exactly like investing.com on weekends. Ticking resumes "
                        f"automatically when Sydney reopens ~Monday 05:00 MYT.", icon=None)
    except Exception:
        pass
    st.divider()

    # ---------------------------------------------------------- verdict row --
    v = sig["verdict"]
    badge_cls = {"BUY": "badge-buy", "SELL": "badge-sell"}.get(v, "badge-wait")
    icon = {"BUY": "🟢 BUY", "SELL": "🔴 SELL"}.get(v, "🟡 WAIT")

    col1, col2, col3, col4, col5 = st.columns([1.35, 1, 1, 1, 1.4])
    with col1:
        st.markdown(f"<span class='badge {badge_cls}'>{icon}</span> "
                    f"<span style='font-size:1.05rem'>confidence "
                    f"<b>{sig['confidence']}%</b></span>", unsafe_allow_html=True)
        st.caption(f"Composite score {sig['score']:+d} / ±100 (trend + structure + RSI + "
                   f"patterns + candles + breakout filter)")
    with col2:
        st.metric("RSI (14)", f"{sig['rsi']:.1f}")
    with col3:
        st.metric("ATR (14)", f"{atr_pips:.0f} pips")
    with col4:
        st.metric("Trend structure", analysis["context"]["structure"].title())
    with col5:
        if plan.get("direction") in ("long", "short"):
            st.metric("Plan risk : reward",
                      f"1 : {plan['rr1']:.1f} → 1 : {plan['rr2']:.1f}")
        else:
            st.metric("Next trigger (buy-stop)", fmt_price(plan["buy_trigger"], digits),
                      f"sell-stop {fmt_price(plan['sell_trigger'], digits)}",
                      delta_color="off")

    # ---------------------------------------------------------------- chart --
    sr_view = support_resistance(df, analysis["atr"])
    has_vol = float(df["volume"].fillna(0).max() or 0) > 0

    zl, zr = st.columns([1.1, 2.4])
    with zl:
        zsel = st.radio("🔍 Zoom", [lab for lab, _ in ZOOM_PRESETS[tf]],
                        index=0, horizontal=True)
    with zr:
        st.markdown("<div class='zoom-hint'>🖱️ scroll wheel = zoom in / out · drag = pan · "
                    "double-click = reset · bottom slider = drag-zoom · newest candle "
                    "moves live</div>", unsafe_allow_html=True)
    zh = dict(ZOOM_PRESETS[tf])[zsel]
    zoom_range = None
    if zh is not None and len(df_disp) > 2:
        bar_dt = df_disp.index[-1] - df_disp.index[-2]
        zoom_range = (df_disp.index[-1] - pd.Timedelta(hours=zh), df_disp.index[-1] + bar_dt)

    fig = build_chart(df_disp, pair, chart_type, sr_view, analysis["patterns"],
                      show_sr=True, show_labels=True,
                      show_volume=has_vol, show_rsi=True, zoom_range=zoom_range,
                      uirevision=f"{pair}|{tf}|{chart_type}|{zsel}")
    st.plotly_chart(fig, key="live_chart", use_container_width=True, config={
        "displayModeBar": "always", "displaylogo": False, "scrollZoom": True,
        "doubleClick": "reset",
        "modeBarButtonsToRemove": ["select2d", "lasso2d", "toggleSpikelines",
                                   "hoverClosestCartesian", "hoverCompareCartesian",
                                   "toggleHover"]})
    if source_used.startswith("Yahoo") and not has_vol:
        st.caption("ℹ️ Yahoo does not publish tick volume for FX — the volume panel is hidden. "
                   "Connect your OANDA token to see live tick volume like TradingView.")


chart_zone = _frag(secs, _chart_zone)


# =========================================================== MTF ZONE (60 s) ==
def _mtf_zone():
    st.subheader("📊 Buy / Sell advice — every timeframe in one table")

    mtf_res = None
    with st.spinner(f"Scanning {pair} on all 6 timeframes (1 min → 1 day)…"):
        try:
            mtf_res = _mtf_scan(pair, source, token, env, int(time.time() // 60))
        except Exception as e:
            st.warning(f"Multi-timeframe scan unavailable: {e}")
    if mtf_res:
        mtf_table = build_mtf_table(pair, mtf_res)
        st.dataframe(table_styler(mtf_table), hide_index=True,
                     use_container_width=True, height=252)
        st.info(f"🎯 {best_setup(mtf_table)}")
        srcs = sorted({r[1] for r in mtf_res.values() if not isinstance(r, Exception)})
        src_txt = f"Data: {', '.join(srcs)} · " if srcs else ""
        st.caption(f"{src_txt}Each row applies the PDF rules on that period (breakout "
                   "filter ≥ 0.1×ATR, stop beyond structure + 0.5×ATR, targets = "
                   "pattern-height projection) · table auto-rescans every 60 s · "
                   "WAIT rows show conditional buy-stop / sell-stop entries.")
        with st.expander("How to read this table"):
            st.markdown(
                "- **Signal** — the engine's verdict for that period: 🟢 BUY / 🔴 SELL / 🟡 WAIT\n"
                "- **Entry** — ideal entry zone now; for WAIT rows, the breakout trigger prices\n"
                "- **Stop loss** — protective stop beyond the last support/resistance (0.5×ATR buffer)\n"
                "- **TP1 / TP2** — first target (next S/R level) and the pattern-height target\n"
                "- **Rule of thumb** — follow the direction the *higher* timeframes agree on; "
                "skip a 5m signal that fights the 1h / 1d trend.")


mtf_zone = _frag(60, _mtf_zone)


# =========================================================== PLAN ZONE (live) ==
def _plan_zone():
    sess = trading_sessions()
    try:
        df, source_used, analysis = _live_analysis(pair, tf, source, token, env,
                                                   n_bars, _live_bucket())
    except Exception as e:
        st.warning(f"Trade plan temporarily unavailable: {e}")
        return

    sig, plan = analysis["signal"], analysis["plan"]
    last_c = float(df["close"].iloc[-1])
    digits = price_digits(pair)
    atr_pips = analysis["atr"] / pip_size(pair)

    # ------------------------------------------------------------- plan -----
    st.subheader("🎯 Trade plan (per the PDF's entry / protective-stop / target rules)")
    if plan.get("direction") in ("long", "short"):
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        d = plan["direction"]
        if d == "long":
            c1.metric("Entry zone (ideal)", fmt_price(plan["entry_ideal"], digits),
                      f"zone {fmt_price(plan['entry_zone'][0], digits)} – {fmt_price(plan['entry_zone'][1], digits)}",
                      delta_color="off")
            c2.metric("Protective stop", fmt_price(plan["stop"], digits),
                      f"-{(plan['entry_ideal'] - plan['stop']) / pip_size(pair):.0f} pips",
                      delta_color="inverse")
            c3.metric("TP 1", fmt_price(plan["tp1"], digits),
                      f"{(plan['tp1'] - plan['entry_ideal']) / pip_size(pair):.0f} pips")
            c4.metric("TP 2 (pattern)", fmt_price(plan["tp2"], digits),
                      f"{(plan['tp2'] - plan['entry_ideal']) / pip_size(pair):.0f} pips")
            c5.metric("Risk / reward", f"1 : {plan['rr1']:.1f}", f"1 : {plan['rr2']:.1f} at TP2")
        else:
            c1.metric("Entry zone (ideal)", fmt_price(plan["entry_ideal"], digits),
                      f"zone {fmt_price(plan['entry_zone'][0], digits)} – {fmt_price(plan['entry_zone'][1], digits)}",
                      delta_color="off")
            c2.metric("Protective stop", fmt_price(plan["stop"], digits),
                      f"+{(plan['stop'] - plan['entry_ideal']) / pip_size(pair):.0f} pips",
                      delta_color="inverse")
            c3.metric("TP 1", fmt_price(plan["tp1"], digits),
                      f"{(plan['entry_ideal'] - plan['tp1']) / pip_size(pair):.0f} pips")
            c4.metric("TP 2 (pattern)", fmt_price(plan["tp2"], digits),
                      f"{(plan['entry_ideal'] - plan['tp2']) / pip_size(pair):.0f} pips")
            c5.metric("Risk / reward", f"1 : {plan['rr1']:.1f}", f"1 : {plan['rr2']:.1f} at TP2")

        # position sizing
        quote = pair.split("/")[1]
        if quote == "USD":
            pip_val = 10.0
        elif pair == "USD/JPY":
            pip_val = 1000.0 / last_c
        else:
            try:
                qdf, _ = fetch_cached(f"USD/{quote}", tf, "Yahoo Finance", "", "Practice (demo)", 5, 300)
                pip_val = 10.0 / float(qdf["close"].iloc[-1]) if quote != "JPY" else \
                          1000.0 / float(qdf["close"].iloc[-1])
            except Exception:
                pip_val = 6.7
        risk_amount = balance * risk_pct / 100.0
        stop_pips = abs(plan["entry_ideal"] - plan["stop"]) / pip_size(pair)
        lots = risk_amount / max(stop_pips * pip_val, 1e-9)
        c6.metric("Size @ risk " + f"{risk_pct:.2f}%",
                  f"{lots:.2f} lots", f"{risk_amount:.0f} USD risk")

        why_l, why_r = st.columns([2, 1])
        with why_l:
            st.markdown("**Why this plan?**")
            for txt, sc in sig["reasons"]:
                arrow = "🟢" if sc > 0 else "🔴" if sc < 0 else "⚪"
                st.markdown(f"- {arrow} {txt} ({sc:+d})")
            if plan.get("pattern"):
                p = plan["pattern"]
                st.info(f"**Pattern engine:** {p['name']} — {p['status']}. {p['rule']}")
            if plan.get("pullback_ok"):
                st.caption("💡 Pattern still *forming*: the PDF prefers waiting for the "
                           "breakout, or entering on the pullback/throwback to the broken "
                           "level after it happens.")
        with why_r:
            st.markdown("**Warnings**")
            if sig["warnings"]:
                for w in sig["warnings"]:
                    st.warning(w)
            else:
                st.caption("No RSI extremes or pattern-quality warnings right now.")
    else:
        b1, b2 = st.columns(2)
        with b1:
            st.markdown("#### 🟢 If price breaks UP")
            st.markdown(
                f"- Buy-stop entry above **{fmt_price(plan['buy_trigger'], digits)}** "
                f"(entry stop per PDF p.11)\n"
                f"- Protective stop **{fmt_price(plan['buy_stop'], digits)}**\n"
                f"- First target **{fmt_price(plan['buy_tp'], digits)}**")
        with b2:
            st.markdown("#### 🔴 If price breaks DOWN")
            st.markdown(
                f"- Sell-stop entry below **{fmt_price(plan['sell_trigger'], digits)}**\n"
                f"- Protective stop **{fmt_price(plan['sell_stop'], digits)}**\n"
                f"- First target **{fmt_price(plan['sell_tp'], digits)}**")
        st.info("⏳ **WAIT verdict** — no pattern is activated and the trend is not clean. "
                "Per the PDF: *a pattern is not complete until an actual breakout occurs.* "
                "The conditional orders above keep you ready for either side.")

    st.success(f"**📌 Conclusion & suggestion — {pair} on {tf}:** {sig['advice']}")

    # ------------------------------------------------- patterns + candles ----
    st.subheader("🧭 What the engine sees right now")
    pl, cr, ind = st.columns([1.35, 1, 1])

    with pl:
        st.markdown("#### Chart patterns (PDF multi-bar)")
        if analysis["patterns"]:
            for p in analysis["patterns"][:5]:
                em = "🟢" if p["direction"] == "bullish" else "🔴" if p["direction"] == "bearish" else "⚪"
                stt = "breakout ✓" if p["status"] == "confirmed breakout" else "forming…"
                tgt = fmt_price(p["target"], digits) if p.get("target") else "—"
                st.markdown(
                    f"{em} **{p['name']}** · {stt}  \n"
                    f"<span class='muted'>level {fmt_price(p['level'], digits)} "
                    f"→ target {tgt}</span>", unsafe_allow_html=True)
            with st.expander("Pattern rules (from the PDF)"):
                for p in analysis["patterns"][:5]:
                    st.markdown(f"**{p['name']}** — {p['rule']}")
        else:
            st.caption("No textbook multi-bar pattern detected in the recent window. "
                       "Price may be trending or ranging without a classic shape — "
                       "the indicator rows below still apply.")

    with cr:
        st.markdown("#### Candlestick signals (PDF)")
        if analysis["candle_signals"]:
            for s_ in analysis["candle_signals"]:
                ic = {"bullish": "🟢", "bearish": "🔴"}.get(s_["direction"], "⚪")
                st.markdown(f"{ic} **{s_['name']}**")
                st.caption(s_["rule"])
        else:
            st.caption("No meaningful candlestick pattern on the last 3 candles.")

    with ind:
        st.markdown("#### Indicator snapshot")
        rsi_v = sig["rsi"]
        st.markdown(f"- **RSI 14:** {rsi_v:.1f} — "
                    f"{'overbought ⚠️' if rsi_v >= 70 else 'oversold ⚠️' if rsi_v <= 30 else 'bullish' if rsi_v >= 55 else 'bearish' if rsi_v <= 45 else 'neutral'}")
        if np.isfinite(sig["sma20"]) and np.isfinite(sig["sma50"]):
            st.markdown(f"- **SMA 20 / 50:** {fmt_price(sig['sma20'], digits)} / "
                        f"{fmt_price(sig['sma50'], digits)} — "
                        f"{'golden alignment (up)' if sig['sma20'] > sig['sma50'] else 'death alignment (down)'}")
        atr_series = df["atr14"].dropna()
        atr_note = "rising" if len(atr_series) > 20 and atr_series.iloc[-1] > atr_series.rolling(20).mean().iloc[-1] \
            else "cooling"
        st.markdown(f"- **ATR 14:** {atr_pips:.0f} pips ({atr_note}) — drives the 0.1×ATR "
                    f"breakout filter and the 0.5×ATR stop buffer")
        st.markdown(f"- **Structure:** {analysis['context']['structure'].title()}")
        b = sig.get("breakout")
        if b:
            st.markdown(f"- **Price is testing {'resistance' if b['side'] == 'up' else 'support'} "
                        f"at {fmt_price(b['level'], digits)}** ({b['touches']} touches)")

    # ----------------------------------------------- timeframe guidance ------
    st.subheader("⏱️ Is this timeframe right for this pair?")
    ga, gb = st.columns([1.15, 1])
    with ga:
        guide = pd.DataFrame([
            ["1 min", "Scalping", "⚡⚡", "Very high — use 2-close confirmation"],
            ["5 min", "Fast intraday", "⚡⚡", "High — confirm every breakout"],
            ["15 min", "Intraday", "⚡", "Moderate — good pattern completion"],
            ["30 min", "Intraday / swing", "⚡", "Moderate-low"],
            ["1 hour", "Swing", "–", "Low — clean breakouts"],
            ["1 day", "Position", "–", "Lowest — most reliable patterns"],
        ], columns=["Timeframe", "Style", "False-breakout risk", "Notes"])
        st.dataframe(guide, hide_index=True, use_container_width=True)
        st.caption("Patterns are fractal — they appear on every period (PDF p.5) — but "
                   "smaller periods show more false breakouts, so confirm before entering.")
    with gb:
        st.info(timeframe_advice(tf, sig, analysis["atr"], last_c, sess))
        st.caption("💡 Rule of thumb: if a 1m/5m setup conflicts with the 1h trend, skip it — "
                   "trade in the direction of the higher timeframe.")


plan_zone = _frag(secs, _plan_zone)

# fallback for old Streamlit versions without fragments: refresh the whole page
if not hasattr(st, "fragment") and secs:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=secs * 1000, key="fx_auto")
    except Exception:
        pass


# ============================================================== BRAND BAR ====
sess = trading_sessions()
live_bits = (f"<span class='live-dot'></span><span class='muted' "
             f"style='font-size:.8rem'>LIVE · ticks every {live_every}</span>"
             if secs else
             "<span class='muted' style='font-size:.8rem'>⏸ live feed off</span>")
st.markdown(
    f"<div class='brand'>"
    f"<img src='{STATIC_BASE}/icon-192.png' width='34' style='border-radius:8px' alt='FX Live Analyst'>"
    f"<span class='brand-name'>FX <span>LIVE</span> ANALYST</span>"
    f"<span class='chip'>v2.2</span>"
    f"<span class='chip'>{pair} · {tf}</span>"
    f"<span style='flex:1'></span>"
    f"{live_bits}"
    f"<span class='chip'>🕒 {sess['myt'].strftime('%a %H:%M')} MYT</span>"
    f"</div>",
    unsafe_allow_html=True)

# ============================================================ RENDER ZONES ====
# Opening the app immediately shows the full analysis — no button to press.
chart_zone()      # price strip + verdict + live chart   (ticks every 3–30 s)
mtf_zone()        # all-timeframe advice table           (rescans every 60 s)
plan_zone()       # trade plan + patterns + guidance     (ticks every 3–30 s)


# ================================================================ WATCHLIST ===
def _watch_zone():
    st.subheader("📋 Multi-pair watchlist (majors)")
    wl_df = _watch(tuple(WATCHLIST), tf, int(time.time() // 60))
    wl_show = wl_df.copy()
    if wl_show["Price"].notna().any():
        d_ = wl_show["Pair"].str.endswith("JPY").map({True: 3, False: 5})
        wl_show["Price"] = [f"{p:.{k}f}" if np.isfinite(p) else "—" for p, k in zip(wl_show["Price"], d_)]
        wl_show["Δ %"] = wl_show["Δ %"].map(lambda v: f"{v:+.2f}%" if np.isfinite(v) else "—")
        wl_show["RSI"] = wl_show["RSI"].map(lambda v: f"{v:.1f}" if np.isfinite(v) else "—")
        st.dataframe(wl_show, hide_index=True, use_container_width=True)
        st.caption(f"Scan uses the **{tf}** timeframe · Yahoo feed · refreshes every 60 s")
    else:
        st.caption("Watchlist temporarily unavailable (data feed hiccup).")


watch_zone = _frag(60, _watch_zone)
watch_zone()

st.divider()
with st.expander("📲 Install on your phone & Google Play Store"):
    st.markdown(
        "**FX LIVE ANALYST** is a web app (PWA) — it installs with its own icon and "
        "full screen, and can later be published on Google Play:\n\n"
        "1. **Host it online, free & 24h** — upload this folder to "
        "[share.streamlit.io](https://share.streamlit.io) and you get a permanent "
        "link that works even when your computer is off (click-by-click steps in the README).\n"
        "2. **Install as an app** — open the link on your phone → browser menu → "
        "**“Add to Home screen”** — the FX icon appears like any other app.\n"
        "3. **Google Play Store** — Play only accepts Android packages: wrap the "
        "hosted link at [PWABuilder.com](https://www.pwabuilder.com) (free) into an "
        "APK/AAB, then publish with a Google Play Developer account (USD 25, "
        "one-time). Full walkthrough in the README.")
st.markdown("<span class='footer-note'>⚠️ Educational software only — nothing here is "
            "financial advice. Forex trading involves substantial risk of loss; past "
            "performance is no guarantee of future results (as the Fidelity PDF itself "
            "reminds us). Always use a practice account first.</span>",
            unsafe_allow_html=True)
