#!/usr/bin/env python3
"""
Production‑hardened stock indicator analyzer.
Fetches OHLCV data from GitHub, computes 30+ technical indicators,
and writes per‑ticker JSON files for front‑end consumption.

Designed for:
- Drop‑in replacement in existing GitHub repo
- Reliable GitHub Actions execution
- Full backward compatibility with existing JSON structure
"""

import json
import logging
import math
import os
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =============================================================================
# CONFIGURATION (original constants preserved)
# =============================================================================
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/subhajitdeo/shape.dna/main/data"
PROCESSED_DIR = "data/processed"
MIN_DAYS = 30

# GitHub API base for listing files
GITHUB_API_URL = "https://api.github.com/repos/subhajitdeo/shape.dna/contents/data"

# Maximum workers for parallel ticker processing
MAX_WORKERS = 4  # reduce if GitHub rate limits become an issue

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Ensure output directory exists
os.makedirs(PROCESSED_DIR, exist_ok=True)


# =============================================================================
# NETWORK & RETRY UTILITIES
# =============================================================================
def build_session() -> requests.Session:
    """
    Create a requests Session with retry logic and connection pooling.
    Retries on 5xx, connection errors, and 429 with exponential backoff.
    """
    session = requests.Session()

    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"],
    )
    adapter = HTTPAdapter(
        max_retries=retry_strategy, pool_connections=10, pool_maxsize=10
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Default headers to identify the tool
    session.headers.update(
        {
            "User-Agent": "shape-dna-indicator-analyzer/1.0",
            "Accept": "application/vnd.github.v3+json",
        }
    )
    return session


def fetch_with_rate_limit(
    session: requests.Session, url: str, **kwargs
) -> Optional[requests.Response]:
    """
    Fetch a URL, respecting GitHub rate limits if detected.
    Returns Response on success, None after final failure.
    """
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            response = session.get(url, timeout=30, **kwargs)

            # Check for rate limiting
            if response.status_code == 429 or response.status_code == 403:
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    wait = int(retry_after) + random.uniform(1, 5)
                else:
                    wait = min(60 * (2**attempt), 600)  # exponential backoff

                logger.warning(
                    "Rate limited (%s). Waiting %.1f seconds...", url, wait
                )
                time.sleep(wait)
                continue

            # Server error -> retry
            if response.status_code >= 500:
                time.sleep(2**attempt)
                continue

            return response
        except (requests.RequestException, ConnectionError) as e:
            logger.warning("Request failed (attempt %d/%d): %s", attempt + 1, max_attempts, e)
            time.sleep(2**attempt)

    return None


# =============================================================================
# DATA VALIDATION UTILITIES
# =============================================================================
def validate_candle(row: Dict[str, Any]) -> bool:
    """Check that a candle dict contains all required numeric fields."""
    required = {"open", "high", "low", "close", "volume", "time"}
    if not required.issubset(row.keys()):
        return False
    try:
        for key in ["open", "high", "low", "close"]:
            val = float(row[key])
            if not math.isfinite(val) or val <= 0:
                return False
        vol = float(row["volume"])
        if not math.isfinite(vol) or vol < 0:
            return False
        # time field must be a parsable date
        datetime.fromisoformat(row["time"])
    except (ValueError, TypeError):
        return False
    return True


def clean_candles(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate, deduplicate, sort, and remove corrupted candles.
    Returns a clean list of dicts.
    """
    if not rows:
        return []

    # Filter invalid rows
    clean = [r for r in rows if validate_candle(r)]

    # Deduplicate by timestamp (keep last occurrence)
    seen = {}
    for r in clean:
        seen[r["time"]] = r
    clean = list(seen.values())

    # Sort chronologically
    clean.sort(key=lambda x: x["time"])

    # Re-check minimum required days after cleaning
    if len(clean) < MIN_DAYS:
        logger.info("After cleaning only %d candles remain (min %d)", len(clean), MIN_DAYS)
        return []

    return clean


def parse_candles(data: Any) -> List[Dict[str, Any]]:
    """
    Parse Yahoo Finance JSON format (or list of dicts) into candle rows.
    Handles both 'chart.result' and list formats.
    """
    rows = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        chart = data.get("chart", {})
        result = chart.get("result", [])
        if not result:
            return []
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        for i in range(len(timestamps)):
            try:
                o = quotes["open"][i]
                h = quotes["high"][i]
                l = quotes["low"][i]
                c = quotes["close"][i]
                v = quotes["volume"][i]
            except (KeyError, IndexError, TypeError):
                continue
            if None in (o, h, l, c, v):
                continue
            try:
                dt = datetime.fromtimestamp(timestamps[i], tz=timezone.utc).strftime("%Y-%m-%d")
            except (TypeError, OverflowError, OSError):
                continue
            rows.append(
                {
                    "time": dt,
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": int(v),
                }
            )
    return rows


# =============================================================================
# FIXED INDICATOR FUNCTIONS (mathematical corrections applied)
# =============================================================================

def ema(values: np.ndarray, period: int) -> np.ndarray:
    """
    Exponential Moving Average with SMA as initial value to reduce bias.
    Returns array same length as values.
    """
    if len(values) < period:
        return values.copy()
    alpha = 2 / (period + 1)
    result = np.empty_like(values)
    result[: period - 1] = np.nan  # insufficient data for full EMA
    result[period - 1] = np.mean(values[:period])
    for i in range(period, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result


def sma(values: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average."""
    out = np.full_like(values, np.nan)
    if len(values) >= period:
        out[period - 1 :] = np.convolve(values, np.ones(period) / period, mode="valid")
    return out


def rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Wilder smoothed RSI.
    Returns array of RSI values (same length as closes, NaN before `period+1`).
    """
    rsi_vals = np.full_like(closes, np.nan)
    if len(closes) < period + 1:
        return rsi_vals
    delta = np.diff(closes)
    gains = np.where(delta > 0, delta, 0)
    losses = np.where(delta < 0, -delta, 0)

    # Initial average gains/losses (simple mean of first `period` values)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()

    # First RSI value at index = period (i.e., after `period` differences)
    rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
    rsi_vals[period] = 100 - (100 / (1 + rs))

    # Wilder smoothing for the rest
    alpha = 1 / period
    for i in range(period + 1, len(closes)):
        avg_gain = alpha * gains[i - 1] + (1 - alpha) * avg_gain
        avg_loss = alpha * losses[i - 1] + (1 - alpha) * avg_loss
        rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
        rsi_vals[i] = 100 - (100 / (1 + rs))
    return rsi_vals


def stoch_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Stochastic of RSI."""
    rsi_vals = rsi(closes, period)
    stoch = np.full_like(closes, np.nan)
    for i in range(period * 2 - 1, len(closes)):  # need at least 2*period points for reliable stoch
        window = rsi_vals[i - period + 1 : i + 1]
        if np.all(np.isfinite(window)):
            min_rsi = np.min(window)
            max_rsi = np.max(window)
            if max_rsi - min_rsi == 0:
                stoch[i] = 50
            else:
                stoch[i] = (window[-1] - min_rsi) / (max_rsi - min_rsi) * 100
    return stoch


def macd(
    closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    MACD line, signal line, histogram.
    Returns (macd_line, signal_line, histogram) each same length as closes.
    """
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Wilder smoothed ATR.
    """
    tr = np.maximum(high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1]))
    atr_vals = np.full_like(high, np.nan)
    if len(tr) < period:
        return atr_vals
    # Initial simple average of first `period` TR values
    atr_vals[period] = tr[:period].mean()
    alpha = 1 / period
    for i in range(period + 1, len(high)):
        atr_vals[i] = alpha * tr[i - 1] + (1 - alpha) * atr_vals[i - 1]
    return atr_vals


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """
    True ADX using Wilder smoothing of +DM, -DM, TR, and DX.
    Returns ADX array (NaN where insufficient data).
    """
    tr = np.maximum(high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1]))
    up_move = high[1:] - high[:-1]
    down_move = low[:-1] - low[1:]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    atr_smooth = np.full_like(high, np.nan)
    plus_di = np.full_like(high, np.nan)
    minus_di = np.full_like(high, np.nan)
    adx_vals = np.full_like(high, np.nan)

    if len(tr) < period:
        return adx_vals

    # Initial Wilder averages (period = given period)
    atr_smooth[period] = tr[:period].mean()
    plus_dm_smooth = plus_dm[:period].mean()
    minus_dm_smooth = minus_dm[:period].mean()

    alpha = 1 / period
    for i in range(period, len(tr)):
        atr_smooth[i] = alpha * tr[i] + (1 - alpha) * atr_smooth[i - 1]
        plus_dm_smooth = alpha * plus_dm[i] + (1 - alpha) * plus_dm_smooth
        minus_dm_smooth = alpha * minus_dm[i] + (1 - alpha) * minus_dm_smooth

        if atr_smooth[i] != 0:
            plus_di[i] = 100 * plus_dm_smooth / atr_smooth[i]
            minus_di[i] = 100 * minus_dm_smooth / atr_smooth[i]

    # DX = 100 * |+DI - -DI| / (+DI + -DI)
    dx = np.full_like(high, np.nan)
    for i in range(period, len(high)):
        if plus_di[i] is not np.nan and minus_di[i] is not np.nan:
            di_sum = plus_di[i] + minus_di[i]
            if di_sum != 0:
                dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum

    # ADX = EMA of DX (period = given period)
    adx_vals = ema(dx, period)
    return adx_vals


def supertrend(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 10, multiplier: float = 3.0
) -> np.ndarray:
    """
    Proper SuperTrend calculation.
    Returns array with values: 1 for uptrend (BUY), -1 for downtrend (SELL), 0 for neutral.
    """
    st = np.zeros_like(close, dtype=int)
    if len(high) < period + 1:
        return st

    atr_vals = atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr_vals
    lower_band = hl2 - multiplier * atr_vals

    trend = np.ones_like(close, dtype=bool)  # True = uptrend
    for i in range(period, len(close)):
        if trend[i - 1]:
            if close[i] < lower_band[i - 1]:
                trend[i] = False  # flip to downtrend
            else:
                trend[i] = True
                # adjust lower band only if it would move up
                lower_band[i] = max(lower_band[i], lower_band[i - 1])
        else:
            if close[i] > upper_band[i - 1]:
                trend[i] = True
            else:
                trend[i] = False
                upper_band[i] = min(upper_band[i], upper_band[i - 1])

    st[trend] = 1
    st[~trend] = -1
    return st


def ichimoku(
    high: np.ndarray, low: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Full Ichimoku components: Tenkan, Kijun, Senkou A, Senkou B, Chikou.
    All returned arrays same length as input.
    """
    n = len(high)
    tenkan = np.full(n, np.nan)
    kijun = np.full(n, np.nan)
    senkou_a = np.full(n, np.nan)
    senkou_b = np.full(n, np.nan)
    chikou = np.full(n, np.nan)

    if n < 52:
        return tenkan, kijun, senkou_a, senkou_b, chikou

    for i in range(9, n):
        tenkan[i] = (np.max(high[i - 9 : i + 1]) + np.min(low[i - 9 : i + 1])) / 2
    for i in range(26, n):
        kijun[i] = (np.max(high[i - 26 : i + 1]) + np.min(low[i - 26 : i + 1])) / 2

    # Senkou A = (Tenkan + Kijun) / 2 plotted 26 periods ahead
    for i in range(26, n - 26):
        if np.isfinite(tenkan[i]) and np.isfinite(kijun[i]):
            senkou_a[i + 26] = (tenkan[i] + kijun[i]) / 2

    # Senkou B = (highest high + lowest low)/2 over 52 periods, plotted 26 ahead
    for i in range(52, n - 26):
        senkou_b[i + 26] = (
            np.max(high[i - 52 : i + 1]) + np.min(low[i - 52 : i + 1])
        ) / 2

    # Chikou = close plotted 26 periods back
    chikou[26:] = close[:-26] if n > 26 else np.nan

    return tenkan, kijun, senkou_a, senkou_b, chikou


def parabolic_sar(high: np.ndarray, low: np.ndarray, step: float = 0.02, max_step: float = 0.2) -> np.ndarray:
    """
    Classic Parabolic SAR. Returns array: 1 for uptrend, -1 for downtrend.
    """
    n = len(high)
    sar = np.full(n, np.nan)
    trend = np.ones(n, dtype=bool)  # True = uptrend
    if n < 2:
        return np.zeros(n, dtype=int)
    af = step
    ep = high[0]
    sar[0] = low[0]
    for i in range(1, n):
        if trend[i - 1]:
            sar[i] = sar[i - 1] + af * (ep - sar[i - 1])
            sar[i] = min(sar[i], low[i - 1], low[i - 2] if i > 1 else low[i - 1])
            if low[i] < sar[i]:
                trend[i] = False
                sar[i] = ep
                ep = low[i]
                af = step
            else:
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + step, max_step)
        else:
            sar[i] = sar[i - 1] + af * (ep - sar[i - 1])
            sar[i] = max(sar[i], high[i - 1], high[i - 2] if i > 1 else high[i - 1])
            if high[i] > sar[i]:
                trend[i] = True
                sar[i] = ep
                ep = high[i]
                af = step
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + step, max_step)
    return np.where(trend, 1, -1)


def bollinger_bands(closes: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands using sample standard deviation (ddof=1)."""
    mid = sma(closes, period)
    # rolling std
    std = np.full_like(closes, np.nan)
    for i in range(period - 1, len(closes)):
        std[i] = np.std(closes[i - period + 1 : i + 1], ddof=1)
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower


def keltner_channel(high, low, close, period=20, multiplier=2):
    """Keltner Channel using EMA center and Wilder ATR."""
    mid = ema(close, period)
    atr_vals = atr(high, low, close, period)
    upper = mid + multiplier * atr_vals
    lower = mid - multiplier * atr_vals
    return upper, mid, lower


def donchian_channel(high: np.ndarray, low: np.ndarray, period: int = 20) -> Tuple[np.ndarray, np.ndarray]:
    """Donchian Channel (highest high and lowest low)."""
    n = len(high)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    if n >= period:
        for i in range(period - 1, n):
            upper[i] = np.max(high[i - period + 1 : i + 1])
            lower[i] = np.min(low[i - period + 1 : i + 1])
    return upper, lower


def aroon(high: np.ndarray, low: np.ndarray, period: int = 25) -> Tuple[np.ndarray, np.ndarray]:
    """Aroon Up/Down (fixed indexing)."""
    n = len(high)
    up = np.full(n, np.nan)
    down = np.full(n, np.nan)
    if n < period:
        return up, down
    for i in range(period - 1, n):
        window_high = high[i - period + 1 : i + 1]
        window_low = low[i - period + 1 : i + 1]
        # days since high/low (0 = most recent)
        days_since_high = period - 1 - np.argmax(window_high)
        days_since_low = period - 1 - np.argmin(window_low)
        up[i] = ((period - days_since_high) / period) * 100
        down[i] = ((period - days_since_low) / period) * 100
    return up, down


def roc(closes: np.ndarray, period: int = 12) -> np.ndarray:
    """Rate of Change."""
    roc_vals = np.full_like(closes, np.nan)
    if len(closes) > period:
        roc_vals[period:] = (closes[period:] - closes[:-period]) / closes[:-period] * 100
    return roc_vals


def momentum(closes: np.ndarray, period: int = 10) -> np.ndarray:
    """Momentum (difference)."""
    mom = np.full_like(closes, np.nan)
    if len(closes) > period:
        mom[period:] = closes[period:] - closes[:-period]
    return mom


def ultimate_oscillator(high, low, close, period1=7, period2=14, period3=28):
    """Ultimate Oscillator."""
    n = len(close)
    uo = np.full(n, np.nan)
    if n < period3 + 1:
        return uo
    bp = close[1:] - np.minimum(low[1:], close[:-1])
    tr = np.maximum(high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1]))

    def avg(bp_vals, tr_vals, period):
        sum_bp = np.sum(bp_vals[-period:])
        sum_tr = np.sum(tr_vals[-period:])
        return sum_bp / sum_tr if sum_tr > 0 else 0.0

    for i in range(period3, n):
        # slices for bp and tr are offset by 1 (because bp/tr start at index 0 = first diff)
        avg1 = avg(bp[:i], tr[:i], period1)   # using last `period1` elements
        avg2 = avg(bp[:i], tr[:i], period2)
        avg3 = avg(bp[:i], tr[:i], period3)
        uo[i] = (4 * avg1 + 2 * avg2 + avg3) / 7 * 100
    return uo


def mfi(high, low, close, volume, period=14):
    """Money Flow Index."""
    n = len(close)
    mfi_vals = np.full(n, np.nan)
    if n < period + 1:
        return mfi_vals
    typical = (high + low + close) / 3
    money_flow = typical * volume
    pos_flow = np.zeros_like(money_flow)
    neg_flow = np.zeros_like(money_flow)
    for i in range(1, n):
        if typical[i] > typical[i - 1]:
            pos_flow[i] = money_flow[i]
        elif typical[i] < typical[i - 1]:
            neg_flow[i] = money_flow[i]
    for i in range(period, n):
        pos_sum = np.sum(pos_flow[i - period + 1 : i + 1])
        neg_sum = np.sum(neg_flow[i - period + 1 : i + 1])
        if neg_sum == 0:
            mfi_vals[i] = 100.0
        else:
            mr = pos_sum / neg_sum
            mfi_vals[i] = 100 - 100 / (1 + mr)
    return mfi_vals


def cmf(high, low, close, volume, period=20):
    """Chaikin Money Flow."""
    n = len(close)
    cmf_vals = np.full(n, np.nan)
    if n < period:
        return cmf_vals
    hl_diff = high - low
    # multiplier: when high==low -> 0
    multiplier = np.where(hl_diff != 0, ((close - low) - (high - close)) / hl_diff, 0.0)
    mfv = multiplier * volume
    for i in range(period - 1, n):
        cmf_vals[i] = np.sum(mfv[i - period + 1 : i + 1]) / np.sum(volume[i - period + 1 : i + 1])
    return cmf_vals


def ease_of_movement(high, low, volume, period=14):
    """Ease of Movement (EOM)."""
    n = len(high)
    eom = np.full(n, np.nan)
    if n < period + 1:
        return eom
    mid = (high + low) / 2
    dist = np.diff(mid)
    br = volume[1:] / 1e8  # avoid tiny box ratio
    box_ratio = br / (np.abs(high[1:] - low[1:]) + 1e-9)
    emv = dist / box_ratio
    for i in range(period, n):
        eom[i] = np.mean(emv[i - period : i])
    return eom


def obv(closes, volumes):
    """On-Balance Volume."""
    obv_vals = np.cumsum(np.where(np.diff(closes, prepend=closes[0]) > 0, volumes, 
                                  np.where(np.diff(closes, prepend=closes[0]) < 0, -volumes, 0)))
    return obv_vals


def vwap(high, low, close, volume):
    """Typical price * volume / total volume (whole series)."""
    typical = (high + low + close) / 3
    vp = typical * volume
    total_vp = np.sum(vp)
    total_vol = np.sum(volume)
    return total_vp / total_vol if total_vol > 0 else np.nan


def std_deviation(closes, period=20):
    """Standard Deviation (sample) over rolling period."""
    n = len(closes)
    std = np.full(n, np.nan)
    for i in range(period - 1, n):
        std[i] = np.std(closes[i - period + 1 : i + 1], ddof=1)
    return std


# =============================================================================
# SIGNAL GENERATION HELPER
# =============================================================================
def get_signal(buy_cond: bool, sell_cond: bool) -> str:
    if buy_cond:
        return "BUY"
    if sell_cond:
        return "SELL"
    return "NEUTRAL"


# =============================================================================
# PROCESS A SINGLE TICKER
# =============================================================================
def process_ticker(ticker: str, session: requests.Session) -> Optional[Dict]:
    """
    Fetch data, compute indicators, and return the output dict.
    Returns None on total failure, so the caller can skip gracefully.
    """
    logger.info("Processing %s", ticker)

    # -------------------------------------------------------------------------
    # Fetch raw data from GitHub
    # -------------------------------------------------------------------------
    url = f"{GITHUB_RAW_BASE}/{ticker}.NS.json"
    resp = fetch_with_rate_limit(session, url)
    if resp is None or resp.status_code != 200:
        logger.error("Failed to fetch data for %s", ticker)
        return None

    try:
        data = resp.json()
    except ValueError:
        logger.error("Invalid JSON for %s", ticker)
        return None

    rows = parse_candles(data)
    if not rows:
        logger.warning("No valid candle rows parsed for %s", ticker)
        return None

    rows = clean_candles(rows)
    if len(rows) < MIN_DAYS:
        logger.info("Skipping %s: only %d valid candles", ticker, len(rows))
        return None

    # Convert to numpy arrays for vectorised calculations
    closes = np.array([r["close"] for r in rows], dtype=np.float64)
    highs = np.array([r["high"] for r in rows], dtype=np.float64)
    lows = np.array([r["low"] for r in rows], dtype=np.float64)
    volumes = np.array([r["volume"] for r in rows], dtype=np.float64)

    latest_close = closes[-1]
    # -------------------------------------------------------------------------
    # Compute indicators (each returns an array; we take the last valid value)
    # -------------------------------------------------------------------------
    def last_valid(arr: np.ndarray, default=0.0) -> float:
        """Return last non-NaN value, or default if all NaN."""
        valid = arr[~np.isnan(arr)]
        return valid[-1] if len(valid) > 0 else default

    rsi_vals = rsi(closes)
    stoch_rsi_vals = stoch_rsi(closes)
    macd_line, signal_line, hist = macd(closes)
    atr_vals = atr(highs, lows, closes)
    adx_vals = adx(highs, lows, closes)
    supertrend_vals = supertrend(highs, lows, closes)  # 1/-1/0
    ichimoku_components = ichimoku(highs, lows)
    psar_vals = parabolic_sar(highs, lows)
    bb_upper, bb_mid, bb_lower = bollinger_bands(closes)
    kelt_upper, kelt_mid, kelt_lower = keltner_channel(highs, lows, closes)
    donch_upper, donch_lower = donchian_channel(highs, lows)
    aroon_up, aroon_down = aroon(highs, lows)
    roc_vals = roc(closes)
    mom_vals = momentum(closes)
    ultimate_vals = ultimate_oscillator(highs, lows, closes)
    mfi_vals = mfi(highs, lows, closes, volumes)
    cmf_vals = cmf(highs, lows, closes, volumes)
    eom_vals = ease_of_movement(highs, lows, volumes)
    obv_vals = obv(closes, volumes)
    std_vals = std_deviation(closes)

    # EMA/SMA arrays
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema100 = ema(closes, 100)
    ema200 = ema(closes, 200)
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)

    # Latest scalar values (with safe fallback)
    rsi_last = last_valid(rsi_vals, 50)
    stoch_rsi_last = last_valid(stoch_rsi_vals, 50)
    macd_l = last_valid(macd_line, latest_close)
    macd_s = last_valid(signal_line, latest_close)
    macd_h = last_valid(hist, 0)
    cci_last = 0  # we'll compute CCI manually with reliable method
    # CCI
    tp = (highs + lows + closes) / 3
    sma_tp = sma(tp, 20)
    mad = np.full_like(closes, np.nan)
    for i in range(20 - 1, len(tp)):
        mad[i] = np.mean(np.abs(tp[i - 19 : i + 1] - sma_tp[i]))
    cci_vals = (tp - sma_tp) / (0.015 * mad)
    cci_last = last_valid(cci_vals, 0)

    williams_last = 0  # computed below

    # Williams %R (using highs and lows)
    will_vals = np.full_like(closes, np.nan)
    period = 14
    for i in range(period - 1, len(highs)):
        hh = np.max(highs[i - period + 1 : i + 1])
        ll = np.min(lows[i - period + 1 : i + 1])
        if hh != ll:
            will_vals[i] = (hh - closes[i]) / (hh - ll) * -100
        else:
            will_vals[i] = -50
    williams_last = last_valid(will_vals, -50)

    super_signal = "NEUTRAL"
    if supertrend_vals[-1] == 1:
        super_signal = "BUY"
    elif supertrend_vals[-1] == -1:
        super_signal = "SELL"

    ichi_signal = "NEUTRAL"
    # use cloud: if close > Senkou A (plot 26 ahead), but we only have up to last data point,
    # so we use latest close against latest known cloud values (Senkou A at last index)
    senkou_a_last = last_valid(ichimoku_components[2], np.nan)
    senkou_b_last = last_valid(ichimoku_components[3], np.nan)
    if not np.isnan(senkou_a_last):
        if closes[-1] > max(senkou_a_last, senkou_b_last):
            ichi_signal = "BUY"
        elif closes[-1] < min(senkou_a_last, senkou_b_last):
            ichi_signal = "SELL"

    psar_sig = "NEUTRAL"
    if psar_vals[-1] == 1:
        psar_sig = "BUY"
    elif psar_vals[-1] == -1:
        psar_sig = "SELL"

    aroon_up_last = last_valid(aroon_up, 50)
    aroon_down_last = last_valid(aroon_down, 50)

    roc_last = last_valid(roc_vals, 0)
    mom_last = last_valid(mom_vals, 0)
    mfi_last = last_valid(mfi_vals, 50)
    ultimate_last = last_valid(ultimate_vals, 50)
    cmf_last = last_valid(cmf_vals, 0)
    eom_last = last_valid(eom_vals, 0)
    obv_last = obv_vals[-1] if len(obv_vals) > 0 else 0
    obv_prev = obv_vals[-2] if len(obv_vals) > 1 else 0

    bb_upper_l = last_valid(bb_upper, None)
    bb_mid_l = last_valid(bb_mid, None)
    bb_lower_l = last_valid(bb_lower, None)
    kelt_upper_l = last_valid(kelt_upper, None)
    kelt_mid_l = last_valid(kelt_mid, None)
    kelt_lower_l = last_valid(kelt_lower, None)
    donch_upper_l = last_valid(donch_upper, None)
    donch_lower_l = last_valid(donch_lower, None)
    atr_last = last_valid(atr_vals, None)
    std_last = last_valid(std_vals, 0)
    vwap_val = vwap(highs, lows, closes, volumes)
    if np.isnan(vwap_val):
        vwap_val = latest_close

    # -------------------------------------------------------------------------
    # Signal aggregation (EXACT same logic as original, but using computed values)
    # -------------------------------------------------------------------------
    buy_signals = 0
    sell_signals = 0
    total_indicators = 0

    if rsi_last < 30: buy_signals += 1
    elif rsi_last > 70: sell_signals += 1
    total_indicators += 1

    if stoch_rsi_last < 20: buy_signals += 1
    elif stoch_rsi_last > 80: sell_signals += 1
    total_indicators += 1

    if macd_l > macd_s: buy_signals += 1
    elif macd_l < macd_s: sell_signals += 1
    total_indicators += 1

    if cci_last < -100: buy_signals += 1
    elif cci_last > 100: sell_signals += 1
    total_indicators += 1

    if williams_last < -80: buy_signals += 1
    elif williams_last > -20: sell_signals += 1
    total_indicators += 1

    if mfi_last < 20: buy_signals += 1
    elif mfi_last > 80: sell_signals += 1
    total_indicators += 1

    if super_signal == "BUY": buy_signals += 1
    elif super_signal == "SELL": sell_signals += 1
    total_indicators += 1

    ema20_l = last_valid(ema20, latest_close)
    ema50_l = last_valid(ema50, latest_close)
    if latest_close > ema20_l: buy_signals += 1
    else: sell_signals += 1
    total_indicators += 1

    if latest_close > ema50_l: buy_signals += 1
    else: sell_signals += 1
    total_indicators += 1

    if bb_lower_l is not None and latest_close < bb_lower_l: buy_signals += 1
    elif bb_upper_l is not None and latest_close > bb_upper_l: sell_signals += 1
    total_indicators += 1

    final_signal = "NEUTRAL"
    if buy_signals > sell_signals + 2:
        final_signal = "STRONG_BUY"
    elif buy_signals > sell_signals:
        final_signal = "BUY"
    elif sell_signals > buy_signals + 2:
        final_signal = "STRONG_SELL"
    elif sell_signals > buy_signals:
        final_signal = "SELL"

    # -------------------------------------------------------------------------
    # Build output dict (matching original schema exactly)
    # -------------------------------------------------------------------------
    # candles: last 252 days (max) as list of dicts
    candles = rows[-252:]

    output = {
        "symbol": ticker,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "latest_price": round(latest_close, 2),
        "final_signal": final_signal,
        "signal_summary": {
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "total_indicators": total_indicators,
        },
        "candles": candles,
        "indicators": {
            "RSI": {
                "value": round(rsi_last, 2),
                "signal": get_signal(rsi_last < 30, rsi_last > 70),
            },
            "StochasticRSI": {
                "value": round(stoch_rsi_last, 2),
                "signal": get_signal(stoch_rsi_last < 20, stoch_rsi_last > 80),
            },
            "MACD": {
                "value": round(macd_l, 2),
                "signal": get_signal(macd_l > macd_s, macd_l < macd_s),
            },
            "MACD_Histogram": round(macd_h, 2),
            "CCI": {
                "value": round(cci_last, 2),
                "signal": get_signal(cci_last < -100, cci_last > 100),
            },
            "Williams_R": {
                "value": round(williams_last, 2),
                "signal": get_signal(williams_last < -80, williams_last > -20),
            },
            "ROC": {
                "value": round(roc_last, 2),
                "signal": get_signal(roc_last > 0, roc_last < 0),
            },
            "Momentum": {
                "value": round(mom_last, 2),
                "signal": get_signal(mom_last > 0, mom_last < 0),
            },
            "MFI": {
                "value": round(mfi_last, 2),
                "signal": get_signal(mfi_last < 20, mfi_last > 80),
            },
            "Ultimate_Oscillator": {
                "value": round(ultimate_last, 2),
                "signal": get_signal(ultimate_last < 30, ultimate_last > 70),
            },
            "ADX": {
                "value": round(adx_vals[-1], 2) if not np.isnan(adx_vals[-1]) else None,
                "signal": "STRONG" if (not np.isnan(adx_vals[-1]) and adx_vals[-1] > 25) else "WEAK",
            },
            "SuperTrend": {"signal": super_signal},
            "Ichimoku": {"signal": ichi_signal},
            "Parabolic_SAR": {"signal": psar_sig},
            "Aroon": {
                "up": round(aroon_up_last, 2),
                "down": round(aroon_down_last, 2),
                "signal": get_signal(
                    aroon_up_last > 70 and aroon_down_last < 30,
                    aroon_down_last > 70 and aroon_up_last < 30,
                ),
            },
            "EMA20": {
                "value": round(ema20_l, 2),
                "signal": get_signal(latest_close > ema20_l, latest_close < ema20_l),
            },
            "EMA50": {
                "value": round(ema50_l, 2),
                "signal": get_signal(latest_close > ema50_l, latest_close < ema50_l),
            },
            "EMA100": {
                "value": round(last_valid(ema100, latest_close), 2),
                "signal": get_signal(latest_close > last_valid(ema100, latest_close), latest_close < last_valid(ema100, latest_close)),
            },
            "EMA200": {
                "value": round(last_valid(ema200, latest_close), 2),
                "signal": get_signal(latest_close > last_valid(ema200, latest_close), latest_close < last_valid(ema200, latest_close)),
            },
            "SMA20": {
                "value": round(last_valid(sma20, latest_close), 2),
                "signal": get_signal(latest_close > last_valid(sma20, latest_close), latest_close < last_valid(sma20, latest_close)),
            },
            "SMA50": {
                "value": round(last_valid(sma50, latest_close), 2),
                "signal": get_signal(latest_close > last_valid(sma50, latest_close), latest_close < last_valid(sma50, latest_close)),
            },
            "SMA200": {
                "value": round(last_valid(sma200, latest_close), 2),
                "signal": get_signal(latest_close > last_valid(sma200, latest_close), latest_close < last_valid(sma200, latest_close)),
            },
            "BollingerBands": {
                "upper": round(bb_upper_l, 2) if bb_upper_l is not None else None,
                "middle": round(bb_mid_l, 2) if bb_mid_l is not None else None,
                "lower": round(bb_lower_l, 2) if bb_lower_l is not None else None,
                "signal": get_signal(
                    latest_close < bb_lower_l, latest_close > bb_upper_l
                )
                if bb_lower_l is not None
                else "NEUTRAL",
            },
            "KeltnerChannel": {
                "upper": round(kelt_upper_l, 2) if kelt_upper_l is not None else None,
                "middle": round(kelt_mid_l, 2) if kelt_mid_l is not None else None,
                "lower": round(kelt_lower_l, 2) if kelt_lower_l is not None else None,
            },
            "DonchianChannel": {
                "upper": round(donch_upper_l, 2) if donch_upper_l is not None else None,
                "lower": round(donch_lower_l, 2) if donch_lower_l is not None else None,
            },
            "ATR": {
                "value": round(atr_last, 2) if atr_last is not None else None,
            },
            "StandardDeviation": {"value": round(std_last, 2)},
            "OBV": {
                "value": int(obv_last),
                "signal": get_signal(obv_last > obv_prev, obv_last < obv_prev)
                if len(obv_vals) > 1
                else "NEUTRAL",
            },
            "CMF": {
                "value": round(cmf_last, 4),
                "signal": get_signal(cmf_last > 0, cmf_last < 0),
            },
            "VWAP": {
                "value": round(vwap_val, 2),
                "signal": get_signal(latest_close > vwap_val, latest_close < vwap_val),
            },
            "EaseOfMovement": {"value": round(eom_last, 4)},
        },
    }

    # Atomic write to prevent corruption
    tmp_path = os.path.join(PROCESSED_DIR, f".{ticker}.tmp")
    final_path = os.path.join(PROCESSED_DIR, f"{ticker}.json")
    try:
        with open(tmp_path, "w") as f:
            json.dump(output, f, indent=2)
        os.replace(tmp_path, final_path)  # atomic on Unix
    except Exception as e:
        logger.exception("Failed to write JSON for %s", ticker)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None

    logger.info("%s processed: price=%.2f, signal=%s", ticker, latest_close, final_signal)
    return output


# =============================================================================
# MAIN ORCHESTRATION
# =============================================================================
def get_available_tickers(session: requests.Session) -> List[str]:
    """Fetch list of .NS.json filenames from GitHub API."""
    logger.info("Fetching ticker list from GitHub...")
    resp = fetch_with_rate_limit(session, GITHUB_API_URL)
    if resp is None or resp.status_code != 200:
        logger.warning("GitHub API error; using fallback Nifty 50 tickers")
        return [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
            "HINDUNILVR", "SBIN", "BHARTIARTL", "KOTAKBANK", "ITC",
            "AXISBANK", "LT", "WIPRO", "HCLTECH", "SUNPHARMA"
        ]

    try:
        contents = resp.json()
        tickers = []
        for item in contents:
            name = item.get("name", "")
            if name.endswith(".NS.json"):
                tickers.append(name.replace(".NS.json", ""))
        logger.info("Found %d tickers", len(tickers))
        return tickers
    except ValueError:
        logger.error("Invalid GitHub API response, using fallback")
        return [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
            "HINDUNILVR", "SBIN", "BHARTIARTL", "KOTAKBANK", "ITC",
        ]


def main():
    session = build_session()
    tickers = get_available_tickers(session)

    # Process sequentially with optional parallel execution
    # Use ThreadPoolExecutor for speed but be mindful of GitHub rate limits
    successful = 0
    failed = 0
    results = []

    # Small delay between requests to be polite to GitHub
    request_delay = 0.2  # seconds

    def process_with_delay(ticker):
        time.sleep(request_delay * random.uniform(0.8, 1.2))  # jitter
        return process_ticker(ticker, session)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ticker = {executor.submit(process_with_delay, t): t for t in tickers}
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                result = future.result()
                if result:
                    successful += 1
                    results.append(result)
                else:
                    failed += 1
            except Exception:
                logger.exception("Unhandled error processing %s", ticker)
                failed += 1

    # Summary
    logger.info("=" * 60)
    logger.info("PROCESSING COMPLETE")
    logger.info("Successful: %d", successful)
    logger.info("Failed: %d", failed)
    logger.info("Total tickers: %d", len(tickers))
    logger.info("Output directory: %s", PROCESSED_DIR)

    # Generate a simple summary report (can be captured by GitHub Actions)
    print(f"✅ COMPLETED - {successful} success, {failed} failed out of {len(tickers)}")


if __name__ == "__main__":
    main()
