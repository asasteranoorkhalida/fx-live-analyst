# 📈 FX Live Analyst — Live Forex Charts + Pattern-Based Buy/Sell Suggestions

**v2.2** — A Python (Streamlit) app for **live forex trading analysis**, in the
spirit of TradingView and investing.com:

- 🔴 **Truly live chart** — the price strip, last candle, verdict badge and
  trade plan update **automatically every 3 s / 5 s / 10 s / 30 s** (your
  choice) while the tab is open: the newest candle visibly moves up and down
  on its own, a pulsing LIVE badge + tick direction arrow (▲/▼) shows every
  price change, and a **last-price tag** sits on the chart's right edge like
  investing.com
- 🔍 **Full TradingView-style zoom that survives live ticks**: mouse-wheel
  zoom, drag-to-zoom, pan, toolbar zoom buttons, drag range-slider under the
  chart, time-window presets (1H / 4H / 1D / 1W … “ALL”) per timeframe —
  and your zoom/pan position is **kept between automatic refreshes**
- 📊 **Buy / Sell advice for EVERY timeframe in one table** — for the chosen
  pair the scanner runs the whole pattern engine on 1m, 5m, 15m, 30m, 1h and
  1d simultaneously and shows Signal · Confidence · Entry · Stop loss ·
  TP1 · TP2 · R:R · pattern/bias per row, plus the strongest setup highlight;
  the table **rescans itself every 60 s**
- ⚡ **Opens with the analysis already on screen** — app name, chart, verdict,
  all-timeframe table and plan render immediately, no button to press
- 💱 **28 currency pairs** (7 majors + 21 crosses)
- ⏱️ **6 timeframes**: 1 min · 5 min · 15 min · 30 min · 1 hour · 1 day
- 🧠 **Buy / Sell / WAIT verdict with confidence %**, built from the Fidelity
  webinar PDF *“Identifying Chart Patterns with Technical Analysis”*:
  - Chart patterns: Double/Triple Tops & Bottoms, Rectangles, Symmetrical /
    Ascending / Descending Triangles, Wedges, Head & Shoulders
  - Candlesticks: Doji, Harami, Hammer/Hanging Man, Shooting Star /
    Inverted Hammer, Engulfing, Piercing Line / Dark Cloud Cover
  - Indicators: SMA 20/50 trend filter, RSI(14), ATR(14) volatility
- 🎯 **Full trade plan**: best entry zone, protective stop, TP1/TP2,
  risk-reward, and suggested position size
- 📏 Auto **support/resistance lines**, **pattern labels on the chart**,
  **volume panel**, **RSI panel**, **multi-pair watchlist**
- 🌏 Chart times shown in **Malaysian time (MYT)** with live session chips
  (Sydney / Tokyo / London / New York)
- 📲 **Installable on phones (PWA)** with its own app icon — and ready for the
  Google Play Store route (see “Phone & Play Store” below)

> ⚠️ Educational tool only — **not financial advice**. Trade at your own risk,
> always on a **practice/demo account** first.

---

## 🚀 From zero to running — full beginner guide

### STEP 0 — What you need
- A Windows / macOS / Linux computer with internet
- ~10 minutes

### STEP 1 — Install Python
1. Go to **https://www.python.org/downloads/** and click the big yellow
   **Download Python 3.12** button.
2. Run the installer. On the **very first screen, tick ✅ “Add python.exe to
   PATH”** (Windows) — this is the step most beginners miss.
3. Click *Install Now*, wait, then close.
4. **Verify:** open a terminal —
   - Windows: press `Win + R`, type `cmd`, press Enter
   - macOS: press `Cmd + Space`, type `terminal`, press Enter
   - Linux: open any terminal
   Then type:
   ```bash
   python --version
   ```
   You should see something like `Python 3.12.x`.
   (If Windows says “python not found”, try `py --version` instead.)

### STEP 2 — Get the app folder
Put the `forex-app` folder somewhere easy, e.g. `C:\forex-app` (Windows) or
`~/forex-app` (macOS/Linux). It contains:

| File | Purpose |
|---|---|
| `app.py` | The main application (UI + live chart) |
| `data_feed.py` | OANDA v20 + Yahoo Finance live data |
| `mtf.py` | Multi-timeframe scanner (all-6-period advice table) |
| `chart_patterns.py` | PDF chart-pattern engine (H&S, triangles, …) |
| `candle_patterns.py` | PDF candlestick engine (engulfing, doji, …) |
| `indicators.py` | SMA / RSI / ATR calculations |
| `signals.py` | Buy/Sell verdict + entry/stop/take-profit logic |
| `chart_view.py` | Plotly chart builder (zoom, slider, pattern labels) |
| `static/` | App icon + PWA manifest (phone install / Play Store) |
| `.streamlit/config.toml` | Dark theme + static file serving |
| `DEPLOY-WEBSITE.md` | **Turn it into a public website — click-by-click (no commands)** |
| `requirements.txt` | The list of libraries to install |

### STEP 3 — Install the libraries
In the terminal, go to the folder and install everything with one command:

**Windows**
```bat
cd C:\forex-app
pip install -r requirements.txt
```
**macOS / Linux**
```bash
cd ~/forex-app
pip3 install -r requirements.txt
```
Wait for “Successfully installed …” (1–3 minutes).

### STEP 4 — (Optional but recommended) Get your free OANDA token
The app works instantly with **Yahoo Finance (free, no key, ~1 min delayed)**.
For broker-grade live rates **and tick volume**, connect OANDA:

1. Create a free practice (demo) account at **https://www.oanda.com/**
   (choose *fxTrade Practice*).
2. Log in → **My Account → Manage API Access → Generate token**.
3. Copy the token string.
4. In the app sidebar, select *OANDA v20*, paste the token, keep
   **Practice (demo)** selected.
   - Never share this token. Switch to “Live (real)” only if you know what
     you are doing.

### STEP 5 — Run the app 🎉
```bash
streamlit run app.py
```
Your browser opens automatically at **http://localhost:8501**.

### STEP 6 — How to use it
1. **Sidebar → Currency pair**: pick any of the 28 pairs (e.g. `EUR/USD`).
2. **Sidebar → Timeframe**: `1 min … 1 day`.
3. **Chart type**: Candlestick (default), Line, or Area.
4. Read the top bar: big **BUY / SELL / WAIT badge** with confidence %,
   RSI, ATR, trend structure, and which trading sessions are open.
5. **📊 Buy / Sell advice table** — right under the verdict: the scanner
   runs all 6 timeframes at once and shows, per period, the signal
   (🟢 BUY / 🔴 SELL / 🟡 WAIT), confidence %, entry, stop loss, TP1/TP2,
   and the pattern or bias driving it. The 🎯 banner below the table names
   the **strongest setup right now**. Rule of thumb: trade in the direction
   the higher timeframes agree on.
6. **Zoom the chart**: scroll the mouse wheel to zoom, drag on the chart to
   zoom into an area, double-click to reset, use the 🔍 Zoom presets
   (12H / 1D / 2D / ALL …) above the chart, or drag the **range slider**
   under the chart. The toolbar at the top-right of the chart has
   zoom-in / zoom-out / pan / autoscale buttons too.
7. Scroll to **Trade plan** → best entry zone, protective stop,
   TP1 / TP2, risk-reward, and suggested lot size.
8. **Conclusion & suggestion** box tells you in plain language whether the
   chosen pair + timeframe currently favours buying, selling, or waiting —
   and why (which pattern/indicators fired).
9. Keep **Live feed** on (sidebar, default **2 s turbo ticks** — options 1 s
   to 30 s) so the price strip and the newest candle move tick-by-tick like
   investing.com — no clicking needed, the app runs **24h** while the tab is
   open, and your zoom position is never lost between ticks. Every tick pulls
   a fresh quote (Yahoo's light quote API, or true streaming bid/ask when your
   OANDA token is set) and the newest candle is *grown* with it — you literally
   watch it rise and fall.

   > 😴 **Weekend note** — the real FX market rests from Sat ~05:00 MYT to Mon
   > ~05:00 MYT. During the weekend every platform (including investing.com)
   > freezes at Friday's close; the app shows a “market is resting” banner and
   > resumes ticking automatically on Monday.

### Troubleshooting
| Problem | Fix |
|---|---|
| `pip` not recognised | Re-install Python and tick “Add to PATH”, or use `py -m pip install -r requirements.txt` |
| Chart empty / “no data” | Market may be closed (weekends); try again Monday, or switch pair |
| OANDA error 401 | Token is wrong/expired — regenerate it, or use Yahoo feed |
| Port 8501 busy | Run `streamlit run app.py --server.port 8502` |

---

## 📲 Phone & Google Play Store

> 🌍 **Shortcut — the full click-by-click website guide is in
> [`DEPLOY-WEBSITE.md`](DEPLOY-WEBSITE.md)** (GitHub upload + Streamlit Cloud +
> phone install + Play Store, zero command prompts).

The app is a **PWA-ready web app** (icon + manifest included in `static/`).
There are 3 levels of “app”:

### Level 1 — Run it online 24h (free, ~10 minutes)
1. Create a free GitHub account (github.com) and a free
   [Streamlit Community Cloud](https://share.streamlit.io) account (sign in
   with GitHub).
2. Create a new **public repository** (e.g. `fx-live-analyst`) and upload all
   the app files (GitHub web → *Add file → Upload files* — drag the whole
   content of the `forex-app` folder; keep `app.py` at the top level).
3. In Streamlit Cloud: **New app → pick the repo → main branch → app path
   `app.py` → Deploy**. After 2–3 minutes you get a permanent link like
   `https://yourname-fx-live-analyst.streamlit.app` that runs **24h even when
   your PC is off**.

### Level 2 — Install it on any phone (no Play Store needed)
1. Open the Level-1 link in Chrome (Android) or Safari (iPhone).
2. Browser menu → **“Add to Home screen”**.
3. The **FX LIVE ANALYST icon** appears on the phone — it opens full-screen,
   exactly like a native app.

### Level 3 — Publish on Google Play Store
Google Play only accepts Android packages (APK/AAB), so you wrap the online
link:
1. Complete **Level 1** (the app must be hosted online).
2. Go to **https://www.pwabuilder.com**, paste your app link, and generate an
   **Android package** (it uses the manifest + icons already included).
   Alternatives: Median.co, WebIntoApp (free tiers).
3. Register a **Google Play Developer account** (one-time USD 25 at
   play.google.com/console).
4. Upload the generated AAB in the Play Console → fill the store listing →
   submit for review.
> Notes: a wrapper app simply shows your hosted app; keep the Streamlit Cloud
> URL alive. Google reviews each submission (usually a few days). The app
> must be online to fetch live prices.

---

## 📚 How the suggestions work (the PDF rules used)

1. **Patterns are fractal** (PDF p.5) — the same shapes are scanned on every
   timeframe you choose.
2. **A pattern is only “activated” by an actual breakout** (PDF p.5) — the
   engine never signals a pattern until price closes beyond its boundary
   (confirmation filter: ≥ 0.1 × ATR beyond the level, two closes preferred,
   PDF p.10).
3. **Entry** — market entry at the confirmed breakout, or on the
   **pullback / throwback** to the broken level (PDF p.15); conditional
   **buy-stop / sell-stop orders** are shown when waiting (PDF p.11).
4. **Protective stop** — placed beyond the support/resistance or swing point
   with a 0.5 × ATR filter (PDF p.13).
5. **Take profit** — the PDF’s measuring rule per pattern: pattern height
   projected from the breakout point (e.g. Double Top p.18, H&S p.27,
   Rectangle p.22, Triangles p.23–25). TP1 uses the nearest opposing
   support/resistance; TP2 uses the full pattern target or 2.5R.
6. **Candlestick context** — reversals only count *after* a meaningful move
   (PDF p.32), and “warning-only” shapes like Hanging Man / Harami are
   reported without scoring, exactly as the PDF advises (pp.34–35).
7. **False-breakout defence** — rectangles and triangles carry a
   “confirm the breakout” note because the PDF flags them for many false
   breakouts (pp.22–23); smaller timeframes get an explicit warning too.

---

## ⚠️ Disclaimer
This software is for **education and research only**. It is not investment
advice, not a solicitation, and carries no warranty. Forex is leveraged and
risky — you can lose more than your deposit. Always confirm signals with your
own analysis and trade on a **demo account** first.
