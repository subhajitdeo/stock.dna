import json
import os
import pandas as pd
import numpy as np
import math
import requests
from datetime import datetime

# ========== CONFIGURATION ==========
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/subhajitdeo/shape.dna/main/data"
PROCESSED_DIR = 'data/processed'
MIN_DAYS = 30

os.makedirs(PROCESSED_DIR, exist_ok=True)

# ========== FETCH FUNCTIONS ==========
def get_available_tickers():
    """Get list of available .NS.json files from GitHub"""
    api_url = "https://api.github.com/repos/subhajitdeo/shape.dna/contents/data"
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            contents = response.json()
            tickers = []
            for item in contents:
                if item['name'].endswith('.NS.json'):
                    ticker = item['name'].replace('.NS.json', '')
                    tickers.append(ticker)
            return tickers
        else:
            print(f"GitHub API error: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching ticker list: {e}")
        return []

def fetch_ticker_data(ticker):
    """Fetch ticker JSON from GitHub"""
    url = f"{GITHUB_RAW_BASE}/{ticker}.NS.json"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  Failed to fetch {ticker}: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return None

# ========== INDICATOR CALCULATION FUNCTIONS (FIXED) ==========

def ema(values, period):
    """
    Exponential Moving Average.
    Uses SMA for the first value to reduce early bias.
    Returns array of same length as values.
    """
    if len(values) < period:
        return values
    alpha = 2 / (period + 1)
    result = [np.nan] * (period - 1)  # not enough data for full EMA
    # Initial value as SMA of first `period` elements
    result.append(sum(values[:period]) / period)
    for val in values[period:]:
        result.append(alpha * val + (1 - alpha) * result[-1])
    return result

def sma(values, period):
    """Simple Moving Average. Returns last SMA value."""
    if len(values) < period:
        return values[-1] if values else 0
    return sum(values[-period:]) / period

def rsi(closes, period=14):
    """
    Wilder smoothed RSI.
    Returns the latest RSI value (scalar) between 0 and 100.
    """
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # Initial average gains/losses (simple mean of first `period` values)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()

    # Wilder smoothing
    alpha = 1 / period
    for i in range(period, len(gains)):
        avg_gain = alpha * gains[i] + (1 - alpha) * avg_gain
        avg_loss = alpha * losses[i] + (1 - alpha) * avg_loss

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    return max(0.0, min(100.0, rsi_val))

def macd(closes, fast=12, slow=26, signal=9):
    """
    MACD line, signal line, histogram.
    Uses EMA with corrected alignment.
    Returns (macd_line, signal_line, histogram) as scalars.
    """
    if len(closes) < slow:
        return closes[-1], closes[-1], 0.0

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    # MACD line = fast EMA - slow EMA (only where both have values)
    min_len = min(len(ema_fast), len(ema_slow))
    macd_line = [ema_fast[i] - ema_slow[i] for i in range(min_len)]

    # Signal line = EMA of MACD line
    signal_line = ema(macd_line, signal) if len(macd_line) >= signal else macd_line

    hist = macd_line[-1] - signal_line[-1] if signal_line else 0.0
    return macd_line[-1], signal_line[-1] if signal_line else 0.0, hist

def bollinger_bands(closes, period=20, std_dev=2):
    """Bollinger Bands using sample standard deviation (ddof=1)."""
    if len(closes) < period:
        return None, None, None
    recent = closes[-period:]
    sma_val = sum(recent) / period
    std = np.std(recent, ddof=1)  # sample std
    return sma_val + std_dev * std, sma_val, sma_val - std_dev * std

def atr(high, low, close, period=14):
    """
    Wilder smoothed ATR.
    Returns latest ATR value (scalar) or None if insufficient data.
    """
    if len(high) < period + 1:
        return None

    # True Range for each interval
    tr = [max(high[i] - low[i],
              abs(high[i] - close[i-1]),
              abs(low[i] - close[i-1])) for i in range(1, len(high))]

    if len(tr) < period:
        return None

    # Initial ATR = simple average of first `period` TR values
    atr_val = sum(tr[:period]) / period
    alpha = 1 / period

    # Wilder smoothing for the rest
    for i in range(period, len(tr)):
        atr_val = alpha * tr[i] + (1 - alpha) * atr_val

    return atr_val

def obv(closes, volumes):
    """On-Balance Volume."""
    obv_vals = [volumes[0]]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv_vals.append(obv_vals[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            obv_vals.append(obv_vals[-1] - volumes[i])
        else:
            obv_vals.append(obv_vals[-1])
    return obv_vals

def stochastic_rsi(closes, period=14):
    """
    Stochastic of RSI using Wilder‑smoothed RSI.
    Returns a scalar between 0 and 100.
    """
    if len(closes) < period * 2:
        return 50.0

    # Compute full RSI series first (Wilder smoothed)
    rsi_vals = []
    # Use the fixed rsi function iteratively? We'll compute rolling RSI manually
    # for each window to avoid re‑using the function that only returns last.
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    alpha = 1 / period

    # First RSI value at index = period
    rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
    rsi_val = 100 - (100 / (1 + rs))
    rsi_vals.append(rsi_val)

    for i in range(period, len(gains)):
        avg_gain = alpha * gains[i] + (1 - alpha) * avg_gain
        avg_loss = alpha * losses[i] + (1 - alpha) * avg_loss
        rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
        rsi_val = 100 - (100 / (1 + rs))
        rsi_vals.append(rsi_val)

    # Now Stochastic of RSI: take last `period` RSI values
    recent = rsi_vals[-period:]
    min_rsi = min(recent)
    max_rsi = max(recent)
    if max_rsi == min_rsi:
        return 50.0
    return (recent[-1] - min_rsi) / (max_rsi - min_rsi) * 100

def cci(high, low, close, period=20):
    """Commodity Channel Index."""
    if len(close) < period:
        return 0.0
    tp = [(high[i] + low[i] + close[i]) / 3 for i in range(len(close))]
    sma_tp = sum(tp[-period:]) / period
    mad = sum(abs(tp[i] - sma_tp) for i in range(-period, 0)) / period
    if mad == 0:
        return 0.0
    return (tp[-1] - sma_tp) / (0.015 * mad)

def williams_r(high, low, close, period=14):
    """Williams %R."""
    if len(close) < period:
        return -50.0
    highest_high = max(high[-period:])
    lowest_low = min(low[-period:])
    if highest_high == lowest_low:
        return -50.0
    return (highest_high - close[-1]) / (highest_high - lowest_low) * -100

def roc(closes, period=12):
    """Rate of Change."""
    if len(closes) < period + 1:
        return 0.0
    prev = closes[-period-1]
    if prev == 0:
        return 0.0
    return (closes[-1] - prev) / prev * 100

def momentum(closes, period=10):
    """Momentum (difference)."""
    if len(closes) < period + 1:
        return 0.0
    return closes[-1] - closes[-period-1]

def mfi(high, low, close, volume, period=14):
    """Money Flow Index."""
    if len(close) < period + 1:
        return 50.0
    typical = [(high[i] + low[i] + close[i]) / 3 for i in range(len(close))]
    money_flow = [typical[i] * volume[i] for i in range(len(close))]
    pos_flow = [0] * len(close)
    neg_flow = [0] * len(close)

    for i in range(1, len(close)):
        if typical[i] > typical[i-1]:
            pos_flow[i] = money_flow[i]
        elif typical[i] < typical[i-1]:
            neg_flow[i] = money_flow[i]

    pos_sum = sum(pos_flow[-period:])
    neg_sum = sum(neg_flow[-period:])
    if neg_sum == 0:
        return 100.0
    mr = pos_sum / neg_sum
    return 100 - (100 / (1 + mr))

def adx(high, low, close, period=14):
    """
    Wilder smoothed ADX.
    Returns latest ADX value (scalar) or None.
    """
    if len(high) < period + 1:
        return None

    # True Range, +DM, -DM
    tr = []
    plus_dm = []
    minus_dm = []
    for i in range(1, len(high)):
        tr.append(max(high[i] - low[i],
                      abs(high[i] - close[i-1]),
                      abs(low[i] - close[i-1])))
        up = high[i] - high[i-1]
        down = low[i-1] - low[i]
        plus_dm.append(up if (up > down and up > 0) else 0)
        minus_dm.append(down if (down > up and down > 0) else 0)

    if len(tr) < period:
        return None

    # Initial Wilder averages
    atr_val = sum(tr[:period]) / period
    plus_di = sum(plus_dm[:period]) / period
    minus_di = sum(minus_dm[:period]) / period

    alpha = 1 / period
    # Smooth from period onward
    for i in range(period, len(tr)):
        atr_val = alpha * tr[i] + (1 - alpha) * atr_val
        plus_di = alpha * plus_dm[i] + (1 - alpha) * plus_di
        minus_di = alpha * minus_dm[i] + (1 - alpha) * minus_di

    # Latest +DI and -DI
    if atr_val == 0:
        return 0.0
    plus_di_val = 100 * plus_di / atr_val
    minus_di_val = 100 * minus_di / atr_val

    # DX = 100 * |+DI - -DI| / (+DI + -DI)
    di_sum = plus_di_val + minus_di_val
    if di_sum == 0:
        return 0.0
    dx_val = 100 * abs(plus_di_val - minus_di_val) / di_sum

    # ADX is Wilder smoothed DX (period same)
    # We need to simulate an ADX series; we already computed DX for latest,
    # but proper ADX requires a running average of DX. We'll approximate
    # by keeping a running average of DX values computed at each step.
    # We'll compute all DX values and then smooth them.
    dx_vals = []
    atr_run = sum(tr[:period]) / period
    plus_run = sum(plus_dm[:period]) / period
    minus_run = sum(minus_dm[:period]) / period
    for i in range(period, len(tr)):
        atr_run = alpha * tr[i] + (1 - alpha) * atr_run
        plus_run = alpha * plus_dm[i] + (1 - alpha) * plus_run
        minus_run = alpha * minus_dm[i] + (1 - alpha) * minus_run
        if atr_run != 0:
            pdi = 100 * plus_run / atr_run
            mdi = 100 * minus_run / atr_run
            di_sum = pdi + mdi
            dx = 100 * abs(pdi - mdi) / di_sum if di_sum != 0 else 0.0
            dx_vals.append(dx)

    if not dx_vals:
        return None

    # Smooth DX with Wilder's method to get ADX
    adx_smooth = sum(dx_vals[:period]) / period  # initial
    for i in range(period, len(dx_vals)):
        adx_smooth = alpha * dx_vals[i] + (1 - alpha) * adx_smooth

    return adx_smooth

def supertrend(high, low, close, period=10, multiplier=3):
    """
    Proper SuperTrend using ATR and trend‑continuation logic.
    Returns 'BUY' or 'SELL'.
    """
    if len(high) < period + 1:
        return "NEUTRAL"

    # Wilder smoothed ATR
    tr = [max(high[i] - low[i],
              abs(high[i] - close[i-1]),
              abs(low[i] - close[i-1])) for i in range(1, len(high))]
    atr_val = sum(tr[:period]) / period
    alpha = 1 / period
    for i in range(period, len(tr)):
        atr_val = alpha * tr[i] + (1 - alpha) * atr_val

    hl2 = [(high[i] + low[i]) / 2 for i in range(len(high))]
    # Upper/Lower bands
    upper = [hl2[i] + multiplier * atr_val for i in range(len(hl2))]
    lower = [hl2[i] - multiplier * atr_val for i in range(len(hl2))]

    # Trend determination
    trend = [True] * len(high)  # True = uptrend
    for i in range(1, len(high)):
        if trend[i-1]:  # previous was uptrend
            if close[i] <= lower[i-1]:
                trend[i] = False
            else:
                trend[i] = True
                lower[i] = max(lower[i], lower[i-1])
        else:           # previous was downtrend
            if close[i] >= upper[i-1]:
                trend[i] = True
            else:
                trend[i] = False
                upper[i] = min(upper[i], upper[i-1])

    return "BUY" if trend[-1] else "SELL"

def ichimoku(high, low, close):
    """
    Full Ichimoku: Tenkan, Kijun, Senkou A, Senkou B, Chikou.
    Returns signal based on cloud position.
    """
    if len(high) < 52:
        return "NEUTRAL"

    n = len(high)
    # Tenkan‑sen (9‑period)
    tenkan = [(max(high[max(0,i-8):i+1]) + min(low[max(0,i-8):i+1])) / 2 for i in range(n)]
    # Kijun‑sen (26‑period)
    kijun = [(max(high[max(0,i-25):i+1]) + min(low[max(0,i-25):i+1])) / 2 for i in range(n)]

    # Senkou Span A = (Tenkan + Kijun)/2 plotted 26 periods ahead
    senkou_a = [None] * n
    for i in range(26, n-26):
        senkou_a[i+26] = (tenkan[i] + kijun[i]) / 2

    # Senkou Span B = (52‑period high+low)/2 plotted 26 periods ahead
    senkou_b = [None] * n
    for i in range(51, n-26):
        senkou_b[i+26] = (max(high[i-51:i+1]) + min(low[i-51:i+1])) / 2

    # Chikou Span = close shifted 26 periods back
    chikou = [None] * n
    for i in range(26, n):
        chikou[i-26] = close[i]

    # Signal: latest close vs cloud (Senkou A & B at latest index)
    last_a = senkou_a[-1]
    last_b = senkou_b[-1]
    if last_a is not None and last_b is not None:
        if close[-1] > max(last_a, last_b):
            return "BUY"
        elif close[-1] < min(last_a, last_b):
            return "SELL"
    return "NEUTRAL"

def parabolic_sar(high, low, step=0.02, max_step=0.2):
    """Classic Parabolic SAR. Returns 'BUY' if uptrend, else 'SELL'."""
    if len(high) < 2:
        return "NEUTRAL"

    n = len(high)
    sar = [0.0] * n
    trend = [True] * n  # True = uptrend
    af = step
    ep = high[0]
    sar[0] = low[0]

    for i in range(1, n):
        if trend[i-1]:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = min(sar[i], low[i-1], low[i-2] if i > 1 else low[i-1])
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
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = max(sar[i], high[i-1], high[i-2] if i > 1 else high[i-1])
            if high[i] > sar[i]:
                trend[i] = True
                sar[i] = ep
                ep = high[i]
                af = step
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + step, max_step)

    return "BUY" if trend[-1] else "SELL"

def keltner_channel(high, low, close, period=20, multiplier=2):
    if len(close) < period:
        return None, None, None
    ema_val = ema(close, period)[-1]  # uses fixed EMA
    atr_val = atr(high, low, close, period)  # uses fixed ATR
    if atr_val is None:
        return None, None, None
    return ema_val + multiplier * atr_val, ema_val, ema_val - multiplier * atr_val

def donchian_channel(high, low, period=20):
    if len(high) < period:
        return None, None
    return max(high[-period:]), min(low[-period:])

def aroon(high, low, period=25):
    """Fixed Aroon: days since high/low correctly measured from most recent bar."""
    if len(high) < period:
        return 50.0, 50.0
    window_high = high[-period:]
    window_low = low[-period:]
    # Days since highest high (0 = most recent)
    days_since_high = period - 1 - np.argmax(window_high)
    days_since_low = period - 1 - np.argmin(window_low)
    aroon_up = ((period - days_since_high) / period) * 100
    aroon_down = ((period - days_since_low) / period) * 100
    return aroon_up, aroon_down

def ultimate_oscillator(high, low, close, period1=7, period2=14, period3=28):
    if len(close) < period3 + 1:
        return 50.0
    bp = [close[i] - min(low[i], close[i-1]) for i in range(1, len(close))]
    tr = [max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])) for i in range(1, len(close))]

    def avg(arr_bp, arr_tr, period):
        sum_bp = sum(arr_bp[-period:])
        sum_tr = sum(arr_tr[-period:])
        return sum_bp / sum_tr if sum_tr > 0 else 0.0

    avg1 = avg(bp, tr, period1)
    avg2 = avg(bp, tr, period2)
    avg3 = avg(bp, tr, period3)
    return (4 * avg1 + 2 * avg2 + avg3) / 7 * 100

def cmf(high, low, close, volume, period=20):
    if len(close) < period:
        return 0.0
    mfv = []
    for i in range(len(close)):
        if high[i] == low[i]:
            mf = 0.0
        else:
            mf = ((close[i] - low[i]) - (high[i] - close[i])) / (high[i] - low[i])
        mfv.append(mf * volume[i])
    sum_mfv = sum(mfv[-period:])
    sum_vol = sum(volume[-period:])
    return sum_mfv / sum_vol if sum_vol > 0 else 0.0

def ease_of_movement(high, low, volume, period=14):
    if len(high) < period + 1:
        return 0.0
    emv = []
    for i in range(1, len(high)):
        distance = ((high[i] + low[i]) / 2) - ((high[i-1] + low[i-1]) / 2)
        box_ratio = volume[i] / 1e8  # standard scaling
        if high[i] - low[i] != 0:
            box_ratio /= (high[i] - low[i])
        else:
            box_ratio /= 0.0001
        if box_ratio != 0:
            emv.append(distance / box_ratio)
        else:
            emv.append(0.0)
    if len(emv) < period:
        return 0.0
    return sum(emv[-period:]) / period

def std_deviation(closes, period=20):
    if len(closes) < period:
        return 0.0
    recent = closes[-period:]
    return np.std(recent, ddof=1)

def vwap(candles):
    """Volume-Weighted Average Price (whole series)."""
    total_typical = 0.0
    total_volume = 0.0
    for c in candles:
        typical = (c['high'] + c['low'] + c['close']) / 3
        total_typical += typical * c['volume']
        total_volume += c['volume']
    return total_typical / total_volume if total_volume > 0 else 0.0

def get_signal(buy_cond, sell_cond):
    if buy_cond:
        return 'BUY'
    if sell_cond:
        return 'SELL'
    return 'NEUTRAL'

def parse_candles(data):
    """Parse Yahoo Finance JSON format into rows (unchanged)."""
    rows = []
    
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        result = data.get('chart', {}).get('result', [])
        if not result:
            return []
        quotes = result[0].get('indicators', {}).get('quote', [{}])[0]
        timestamps = result[0].get('timestamp', [])
        for i in range(len(timestamps)):
            o = quotes.get('open', [None])[i]
            h = quotes.get('high', [None])[i]
            l = quotes.get('low', [None])[i]
            c = quotes.get('close', [None])[i]
            v = quotes.get('volume', [None])[i]
            if None not in (o, h, l, c, v):
                rows.append({
                    'time': pd.Timestamp(timestamps[i], unit='s').strftime('%Y-%m-%d'),
                    'open': float(o), 'high': float(h), 'low': float(l),
                    'close': float(c), 'volume': int(v)
                })
    return rows

def process_ticker(ticker):
    """Process a single ticker (unchanged apart from using fixed indicator functions)."""
    print(f"\n📊 Processing {ticker}...")
    
    # Fetch data from GitHub
    data = fetch_ticker_data(ticker)
    if not data:
        print(f"  ❌ Failed to fetch data for {ticker}")
        return False
    
    # Parse candles
    rows = parse_candles(data)
    
    if len(rows) < MIN_DAYS:
        print(f"  ⚠️ Only {len(rows)} days (need {MIN_DAYS}), skipping")
        return False
    
    rows.sort(key=lambda x: x['time'])
    
    closes = [r['close'] for r in rows]
    highs = [r['high'] for r in rows]
    lows = [r['low'] for r in rows]
    volumes = [r['volume'] for r in rows]
    latest_close = closes[-1]
    
    # Calculate indicators (with error handling)
    try:
        rsi_val = rsi(closes)
    except:
        rsi_val = 50
    
    try:
        stoch_rsi_val = stochastic_rsi(closes)
    except:
        stoch_rsi_val = 50
    
    try:
        macd_line, macd_sig, macd_hist = macd(closes)
    except:
        macd_line, macd_sig, macd_hist = latest_close, latest_close, 0
    
    try:
        cci_val = cci(highs, lows, closes)
    except:
        cci_val = 0
    
    try:
        williams_val = williams_r(highs, lows, closes)
    except:
        williams_val = -50
    
    try:
        roc_val = roc(closes)
    except:
        roc_val = 0
    
    try:
        mom_val = momentum(closes)
    except:
        mom_val = 0
    
    try:
        mfi_val = mfi(highs, lows, closes, volumes)
    except:
        mfi_val = 50
    
    try:
        adx_val = adx(highs, lows, closes)
    except:
        adx_val = None
    
    try:
        supertrend_signal = supertrend(highs, lows, closes)
    except:
        supertrend_signal = "NEUTRAL"
    
    try:
        ichimoku_signal = ichimoku(highs, lows, closes)
    except:
        ichimoku_signal = "NEUTRAL"
    
    try:
        psar_signal = parabolic_sar(highs, lows)
    except:
        psar_signal = "NEUTRAL"
    
    try:
        aroon_up, aroon_down = aroon(highs, lows)
    except:
        aroon_up, aroon_down = 50, 50
    
    try:
        ultimate_val = ultimate_oscillator(highs, lows, closes)
    except:
        ultimate_val = 50
    
    try:
        cmf_val = cmf(highs, lows, closes, volumes)
    except:
        cmf_val = 0
    
    try:
        emv_val = ease_of_movement(highs, lows, volumes)
    except:
        emv_val = 0
    
    try:
        std_dev_val = std_deviation(closes)
    except:
        std_dev_val = 0
    
    try:
        vwap_val = vwap(rows)
    except:
        vwap_val = latest_close
    
    try:
        obv_vals = obv(closes, volumes)
    except:
        obv_vals = [0]
    
    try:
        bb_upper, bb_mid, bb_lower = bollinger_bands(closes)
    except:
        bb_upper, bb_mid, bb_lower = None, None, None
    
    try:
        atr_val = atr(highs, lows, closes)
    except:
        atr_val = None
    
    try:
        keltner_upper, keltner_mid, keltner_lower = keltner_channel(highs, lows, closes)
    except:
        keltner_upper, keltner_mid, keltner_lower = None, None, None
    
    try:
        donchian_upper, donchian_lower = donchian_channel(highs, lows)
    except:
        donchian_upper, donchian_lower = None, None
    
    # EMAs and SMAs
    try:
        ema20_vals = ema(closes, 20)
        ema20 = ema20_vals[-1] if len(ema20_vals) >= 20 else latest_close
    except:
        ema20 = latest_close
    
    try:
        ema50_vals = ema(closes, 50)
        ema50 = ema50_vals[-1] if len(ema50_vals) >= 50 else latest_close
    except:
        ema50 = latest_close
    
    try:
        ema100_vals = ema(closes, 100)
        ema100 = ema100_vals[-1] if len(ema100_vals) >= 100 else latest_close
    except:
        ema100 = latest_close
    
    try:
        ema200_vals = ema(closes, 200)
        ema200 = ema200_vals[-1] if len(ema200_vals) >= 200 else latest_close
    except:
        ema200 = latest_close
    
    try:
        sma20 = sma(closes, 20)
    except:
        sma20 = latest_close
    
    try:
        sma50 = sma(closes, 50)
    except:
        sma50 = latest_close
    
    try:
        sma200 = sma(closes, 200)
    except:
        sma200 = latest_close
    
    # Calculate summary signals (exactly as before)
    buy_signals = 0
    sell_signals = 0
    total_indicators = 0
    
    if rsi_val < 30: buy_signals += 1
    elif rsi_val > 70: sell_signals += 1
    total_indicators += 1
    
    if stoch_rsi_val < 20: buy_signals += 1
    elif stoch_rsi_val > 80: sell_signals += 1
    total_indicators += 1
    
    if macd_line > macd_sig: buy_signals += 1
    elif macd_line < macd_sig: sell_signals += 1
    total_indicators += 1
    
    if cci_val < -100: buy_signals += 1
    elif cci_val > 100: sell_signals += 1
    total_indicators += 1
    
    if williams_val < -80: buy_signals += 1
    elif williams_val > -20: sell_signals += 1
    total_indicators += 1
    
    if mfi_val < 20: buy_signals += 1
    elif mfi_val > 80: sell_signals += 1
    total_indicators += 1
    
    if supertrend_signal == "BUY": buy_signals += 1
    elif supertrend_signal == "SELL": sell_signals += 1
    total_indicators += 1
    
    if latest_close > ema20: buy_signals += 1
    else: sell_signals += 1
    total_indicators += 1
    
    if latest_close > ema50: buy_signals += 1
    else: sell_signals += 1
    total_indicators += 1
    
    if bb_lower and latest_close < bb_lower: buy_signals += 1
    elif bb_upper and latest_close > bb_upper: sell_signals += 1
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
    
    output = {
        'symbol': ticker,
        'updated_at': datetime.now().isoformat(),
        'latest_price': round(latest_close, 2),
        'final_signal': final_signal,
        'signal_summary': {
            'buy_signals': buy_signals,
            'sell_signals': sell_signals,
            'total_indicators': total_indicators
        },
        'candles': rows[-252:],
        'indicators': {
            'RSI': {'value': round(rsi_val, 2), 'signal': get_signal(rsi_val < 30, rsi_val > 70)},
            'StochasticRSI': {'value': round(stoch_rsi_val, 2), 'signal': get_signal(stoch_rsi_val < 20, stoch_rsi_val > 80)},
            'MACD': {'value': round(macd_line, 2), 'signal': get_signal(macd_line > macd_sig, macd_line < macd_sig)},
            'MACD_Histogram': round(macd_hist, 2),
            'CCI': {'value': round(cci_val, 2), 'signal': get_signal(cci_val < -100, cci_val > 100)},
            'Williams_R': {'value': round(williams_val, 2), 'signal': get_signal(williams_val < -80, williams_val > -20)},
            'ROC': {'value': round(roc_val, 2), 'signal': get_signal(roc_val > 0, roc_val < 0)},
            'Momentum': {'value': round(mom_val, 2), 'signal': get_signal(mom_val > 0, mom_val < 0)},
            'MFI': {'value': round(mfi_val, 2), 'signal': get_signal(mfi_val < 20, mfi_val > 80)},
            'Ultimate_Oscillator': {'value': round(ultimate_val, 2), 'signal': get_signal(ultimate_val < 30, ultimate_val > 70)},
            'ADX': {'value': round(adx_val, 2) if adx_val else None, 'signal': 'STRONG' if adx_val and adx_val > 25 else 'WEAK'},
            'SuperTrend': {'signal': supertrend_signal},
            'Ichimoku': {'signal': ichimoku_signal},
            'Parabolic_SAR': {'signal': psar_signal},
            'Aroon': {'up': round(aroon_up, 2), 'down': round(aroon_down, 2), 'signal': get_signal(aroon_up > 70 and aroon_down < 30, aroon_down > 70 and aroon_up < 30)},
            'EMA20': {'value': round(ema20, 2), 'signal': get_signal(latest_close > ema20, latest_close < ema20)},
            'EMA50': {'value': round(ema50, 2), 'signal': get_signal(latest_close > ema50, latest_close < ema50)},
            'EMA100': {'value': round(ema100, 2), 'signal': get_signal(latest_close > ema100, latest_close < ema100)},
            'EMA200': {'value': round(ema200, 2), 'signal': get_signal(latest_close > ema200, latest_close < ema200)},
            'SMA20': {'value': round(sma20, 2), 'signal': get_signal(latest_close > sma20, latest_close < sma20)},
            'SMA50': {'value': round(sma50, 2), 'signal': get_signal(latest_close > sma50, latest_close < sma50)},
            'SMA200': {'value': round(sma200, 2), 'signal': get_signal(latest_close > sma200, latest_close < sma200)},
            'BollingerBands': {'upper': round(bb_upper, 2) if bb_upper else None, 'middle': round(bb_mid, 2) if bb_mid else None, 'lower': round(bb_lower, 2) if bb_lower else None, 'signal': get_signal(latest_close < bb_lower, latest_close > bb_upper) if bb_lower else 'NEUTRAL'},
            'KeltnerChannel': {'upper': round(keltner_upper, 2) if keltner_upper else None, 'middle': round(keltner_mid, 2) if keltner_mid else None, 'lower': round(keltner_lower, 2) if keltner_lower else None},
            'DonchianChannel': {'upper': round(donchian_upper, 2) if donchian_upper else None, 'lower': round(donchian_lower, 2) if donchian_lower else None},
            'ATR': {'value': round(atr_val, 2) if atr_val else None},
            'StandardDeviation': {'value': round(std_dev_val, 2)},
            'OBV': {'value': int(obv_vals[-1]) if obv_vals else None, 'signal': get_signal(obv_vals[-1] > obv_vals[-2], obv_vals[-1] < obv_vals[-2]) if len(obv_vals) > 1 else 'NEUTRAL'},
            'CMF': {'value': round(cmf_val, 4), 'signal': get_signal(cmf_val > 0, cmf_val < 0)},
            'VWAP': {'value': round(vwap_val, 2), 'signal': get_signal(latest_close > vwap_val, latest_close < vwap_val)},
            'EaseOfMovement': {'value': round(emv_val, 4)}
        }
    }
    
    out_path = os.path.join(PROCESSED_DIR, f"{ticker}.json")
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"  ✅ {ticker} - ₹{round(latest_close, 2)} | RSI: {round(rsi_val, 2)} | Signal: {final_signal}")
    return True

# ========== MAIN EXECUTION ==========

def main():
    print("=" * 60)
    print("📈 STOCK MARKET INDICATOR ANALYZER")
    print("=" * 60)
    print("\nFetching ticker list from GitHub...")
    
    tickers = get_available_tickers()
    
    if not tickers:
        print("❌ Could not fetch ticker list. Using fallback Nifty 50 stocks...")
        fallback_tickers = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 
                           'HINDUNILVR', 'SBIN', 'BHARTIARTL', 'KOTAKBANK', 'ITC',
                           'AXISBANK', 'LT', 'WIPRO', 'HCLTECH', 'SUNPHARMA']
        tickers = fallback_tickers
    
    print(f"📊 Found {len(tickers)} tickers to process\n")
    
    successful = 0
    failed = 0
    
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}]", end=" ")
        if process_ticker(ticker):
            successful += 1
        else:
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"✅ COMPLETED!")
    print(f"   Successfully processed: {successful}")
    print(f"   Failed: {failed}")
    print(f"   Total: {len(tickers)}")
    print(f"📁 Results saved to: {PROCESSED_DIR}/")
    print("=" * 60)

if __name__ == "__main__":
    main()
