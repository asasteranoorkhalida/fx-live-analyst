"""
data_feed.py — Live forex data layer.

Primary source : OANDA v20 REST API (practice or live, needs your own API token).
Fallback source: Yahoo Finance (free, no key required, ~1 min delayed).

Both sources return a DataFrame with columns:
    [open, high, low, close, volume]  indexed by datetime (Asia/Kuala_Lumpur)
"""
from __future__ import annotations

import time

import requests
import pandas as pd

# ----------------------------------------------------------------------------- 
# Timeframes: label -> (oanda_granularity, yahoo_interval, cache_ttl_seconds)
# -----------------------------------------------------------------------------
TIMEFRAMES = {
    "1 min":  ("M1", "1m",  30),
    "5 min":  ("M5", "5m",  60),
    "15 min": ("M15", "15m", 120),
    "30 min": ("M30", "30m", 180),
    "1 hour": ("H1", "1h",  300),
    "1 day":  ("D",  "1d",  1800),
}

# Yahoo only keeps limited history for small intervals (7 days max for 1m etc.)
_YF_PERIOD = {"1m": "5d", "5m": "60d", "15m": "60d", "30m": "60d", "1h": "730d", "1d": "2y"}

OANDA_ENVS = {
    "Practice (demo)": "https://api-fxpractice.oanda.com",
    "Live (real)":     "https://api-fxtrade.oanda.com",
}

# 28 tradeable pairs -------------------------------------------------------------
PAIR_GROUPS = {
    "Majors": [
        "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
        "AUD/USD", "NZD/USD", "USD/CAD",
    ],
    "Crosses": [
        "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD", "EUR/CAD", "EUR/NZD",
        "GBP/JPY", "GBP/CHF", "GBP/AUD", "GBP/CAD", "GBP/NZD",
        "AUD/JPY", "AUD/CAD", "AUD/CHF", "AUD/NZD",
        "NZD/JPY", "NZD/CAD", "NZD/CHF",
        "CAD/JPY", "CAD/CHF", "CHF/JPY",
    ],
}
ALL_PAIRS = PAIR_GROUPS["Majors"] + PAIR_GROUPS["Crosses"]
WATCHLIST = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
             "AUD/USD", "NZD/USD", "USD/CAD", "EUR/JPY"]


def pair_to_oanda(pair: str) -> str:
    return pair.replace("/", "_")


def pair_to_yahoo(pair: str) -> str:
    return pair.replace("/", "") + "=X"


def pip_size(pair: str) -> float:
    """0.01 for JPY-quoted pairs, otherwise 0.0001."""
    return 0.01 if pair.endswith("JPY") else 0.0001


def price_digits(pair: str) -> int:
    return 3 if pair.endswith("JPY") else 5


def _to_myt(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Convert index to Asia/Kuala_Lumpur time for display."""
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return idx.tz_convert("Asia/Kuala_Lumpur")


# ------------------------------------------------------------------ OANDA v20 --
def fetch_oanda(pair: str, timeframe: str, token: str, env: str, count: int = 400) -> pd.DataFrame:
    """Fetch candles from OANDA v20. Includes the latest (possibly incomplete)
    candle so the chart is genuinely 'live' while the market is open."""
    gran, _, _ = TIMEFRAMES[timeframe]
    url = f"{OANDA_ENVS[env]}/v3/instruments/{pair_to_oanda(pair)}/candles"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params = {"granularity": gran, "count": min(int(count), 2000), "price": "M"}
    r = requests.get(url, headers=headers, params=params, timeout=15)
    if r.status_code == 401:
        raise RuntimeError("OANDA rejected the token (401 Unauthorized) — check the API token.")
    if r.status_code == 400:
        raise RuntimeError(f"OANDA bad request (400): {r.text[:200]}")
    if r.status_code == 429:
        raise RuntimeError("OANDA rate limit hit (429) — wait a moment and refresh.")
    r.raise_for_status()
    data = r.json()
    rows = []
    for c in data.get("candles", []):
        mid = c.get("mid", {})
        if not mid:
            continue
        rows.append({
            "time": c["time"],
            "open": float(mid["o"]), "high": float(mid["h"]),
            "low": float(mid["l"]), "close": float(mid["c"]),
            "volume": float(c.get("volume", 0) or 0),
        })
    if not rows:
        raise RuntimeError("OANDA returned no candles for this pair/timeframe.")
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], format="ISO8601", utc=True)
    df = df.set_index("time").sort_index()
    df.index = _to_myt(df.index)
    df.index.name = "time"
    return df[["open", "high", "low", "close", "volume"]]


# ----------------------------------------------------------- Yahoo Finance ----
def fetch_yahoo(pair: str, timeframe: str, count: int = 400) -> pd.DataFrame:
    """Free fallback via Yahoo Finance (no API key). Slightly delayed."""
    import yfinance as yf

    _, interval, _ = TIMEFRAMES[timeframe]
    period = _YF_PERIOD[interval]
    df = yf.Ticker(pair_to_yahoo(pair)).history(
        period=period, interval=interval, auto_adjust=True
    )
    if df is None or df.empty:
        raise RuntimeError(f"Yahoo Finance returned no data for {pair} ({timeframe}). "
                           "Try again in a few seconds or switch source.")
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df["volume"] = df["volume"].fillna(0.0)
    df = df.tail(int(count))
    df.index = _to_myt(df.index)
    df.index.name = "time"
    return df


def get_candles(pair: str, timeframe: str, source: str,
                token: str = "", env: str = "Practice (demo)",
                count: int = 400) -> tuple[pd.DataFrame, str]:
    """Unified entry point. Returns (df, source_used).
    Falls back to Yahoo automatically when OANDA is selected but no token given,
    or when the OANDA call fails."""
    if source == "OANDA v20" and token.strip():
        try:
            return fetch_oanda(pair, timeframe, token.strip(), env, count), "OANDA v20"
        except Exception as e:
            df = fetch_yahoo(pair, timeframe, count)
            return df, f"Yahoo Finance (OANDA failed: {e})"
    if source == "OANDA v20":
        df = fetch_yahoo(pair, timeframe, count)
        return df, "Yahoo Finance (add an OANDA token for broker-grade data)"
    return fetch_yahoo(pair, timeframe, count), "Yahoo Finance"


# --------------------------------------------------- live quote (tick feed) --
# The full candle history is cached for tens of seconds, but the price strip and
# the newest candle must move tick-by-tick like investing.com. This section
# provides a very light per-second quote:
#   * OANDA (when the user gave a token) → /accounts/{id}/pricing = true
#     broker-grade bid/ask, refreshed in real time (~250 ms server side);
#   * otherwise a direct call to Yahoo's chart endpoint (no yfinance download,
#     no API key) which returns meta.regularMarketPrice — much fresher and
#     ~20× lighter than a full history pull.
_YF_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
_OANDA_ACC: dict = {}          # hash((token, env)) -> account id (memory only)
_LAST_FAIL = {"t": 0.0}        # brief back-off so we never hammer a grumpy API


def _yahoo_quote(pair: str) -> dict:
    """Keyless spot quote + forming 1-minute candle from Yahoo's chart API."""
    r = requests.get(_YF_CHART_URL.format(sym=pair_to_yahoo(pair)),
                     params={"interval": "1m", "range": "1d",
                             "includePrePost": "false"},
                     headers=_UA, timeout=8)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    meta = res["meta"]
    price = float(meta["regularMarketPrice"])
    ts = int(meta.get("regularMarketTime") or 0)
    myt = pd.Timestamp.now(tz="Asia/Kuala_Lumpur")
    if ts:
        myt = pd.Timestamp(ts, unit="s", tz="UTC").tz_convert("Asia/Kuala_Lumpur")
    candle = None
    try:                                   # newest non-null 1m candle
        q = res["indicators"]["quote"][0]
        for i in range(len(res.get("timestamp") or []) - 1, -1, -1):
            o, h, l, c = (q["open"][i], q["high"][i], q["low"][i], q["close"][i])
            if None in (o, h, l, c):
                continue
            candle = {"time": pd.Timestamp(res["timestamp"][i], unit="s", tz="UTC")
                        .tz_convert("Asia/Kuala_Lumpur"),
                      "open": float(o), "high": float(h),
                      "low": float(l), "close": float(c)}
            break
    except Exception:
        candle = None
    prev = meta.get("previousClose") or meta.get("chartPreviousClose") or price
    return {"price": price, "ts": myt, "candle": candle,
            "prev_close": float(prev) or price, "bid": None, "ask": None}


def _oanda_account_id(token: str, env: str) -> str | None:
    key = hash((token, env))
    if key not in _OANDA_ACC:
        r = requests.get(f"{OANDA_ENVS[env]}/v3/accounts",
                         headers={"Authorization": f"Bearer {token}"}, timeout=8)
        r.raise_for_status()
        accs = r.json().get("accounts", [])
        if not accs:
            return None
        _OANDA_ACC[key] = accs[0]["id"]
    return _OANDA_ACC[key]


def _oanda_quote(pair: str, token: str, env: str) -> dict:
    """True real-time bid/ask from OANDA's pricing endpoint (no lag)."""
    acc = _oanda_account_id(token, env)
    if not acc:
        raise RuntimeError("OANDA returned no accounts for this token")
    r = requests.get(f"{OANDA_ENVS[env]}/v3/accounts/{acc}/pricing",
                     headers={"Authorization": f"Bearer {token}"},
                     params={"instruments": pair_to_oanda(pair)}, timeout=8)
    r.raise_for_status()
    p = r.json()["prices"][0]
    bid = float(p["bids"][0]["price"])
    ask = float(p["asks"][0]["price"])
    ts = pd.Timestamp(p["time"]).tz_convert("Asia/Kuala_Lumpur")
    return {"price": (bid + ask) / 2.0, "ts": ts, "candle": None,
            "prev_close": (bid + ask) / 2.0, "bid": bid, "ask": ask}


def get_live_quote(pair: str, token: str = "",
                   env: str = "Practice (demo)") -> dict | None:
    """Freshest possible price for the live ticker + growing candle.

    OANDA token  → real-time bid/ask poll (broker grade, sub-second moves).
    No token     → Yahoo's lightweight chart API (free, updates every few s).
    Returns None (never raises) when the feed is unreachable or throttled, so
    the chart simply keeps its last known state instead of erroring."""
    if time.time() - _LAST_FAIL["t"] < 6:            # gentle back-off window
        return None
    attempts = []
    if token.strip():
        attempts.append(lambda: _oanda_quote(pair, token.strip(), env))
    attempts.append(lambda: _yahoo_quote(pair))
    for fn in attempts:
        try:
            return fn()
        except Exception:
            continue
    _LAST_FAIL["t"] = time.time()
    return None


# ------------------------------------------------------- Trading sessions -----
def _wrap(x: float, start: float, end: float) -> bool:
    """True if hour x is inside [start, end), handling overnight wrap."""
    return (start <= x < end) if start < end else (x >= start or x < end)


def trading_sessions() -> dict:
    """Which major sessions are open right now (UTC hours), plus MYT clock."""
    now_utc = pd.Timestamp.now(tz="UTC")
    h = now_utc.hour + now_utc.minute / 60.0
    sessions = {
        "Sydney":   _wrap(h, 21, 6),
        "Tokyo":    _wrap(h, 0, 9),
        "London":   _wrap(h, 7, 16),
        "New York": _wrap(h, 12, 21),
    }
    return {
        "sessions": sessions,
        "lon_ny_overlap": _wrap(h, 12, 16),
        "myt": now_utc.tz_convert("Asia/Kuala_Lumpur"),
        "utc": now_utc,
    }
