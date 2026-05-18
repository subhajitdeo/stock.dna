import json
import os
import pandas as pd
import numpy as np
import math
import requests
from io import BytesIO
import zipfile

# ========== CONFIGURATION ==========
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/subhajitdeo/shape.dna/main/data"
PROCESSED_DIR = 'data/processed'
MIN_DAYS = 30

os.makedirs(PROCESSED_DIR, exist_ok=True)

# ========== FETCH FUNCTIONS ==========
def get_available_tickers():
    """Get list of available .NS.json files from GitHub"""
    # GitHub API to list contents
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
            # Fallback to a predefined list or return empty
            return []
    except Exception as e:
        print(f"Error fetching ticker list: {e}")
        return []

def fetch_ticker_data(ticker):
    """Fetch ticker JSON from GitHub"""
    url = f"{GITHUB_RAW_BASE}/{ticker}.NS.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  Failed to fetch {ticker}: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return None

# ========== INDICATOR CALCULATION FUNCTIONS ==========
# [All your existing indicator functions remain exactly the same]
# (ema, sma, rsi, macd, bollinger_bands, atr, obv, stochastic_rsi, cci, 
#  williams_r, roc, momentum, mfi, adx, supertrend, ichimoku, parabolic_sar,
#  keltner_channel, donchian_channel, aroon, ultimate_oscillator, cmf,
#  ease_of_movement, std_deviation, vwap, get_signal)

def ema(values, period):
    if len(values) < period:
        return values
    alpha = 2 / (period + 1)
    result = [values[0]]
    for val in values[1:]:
        result.append(alpha * val + (1 - alpha) * result[-1])
    return result

def sma(values, period):
    if len(values) < period:
        return values[-1] if values else 0
    return sum(values[-period:]) / period

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    avg_gain = sum(gains[-period:]) / period if len(gains) >= period else (sum(gains) / len(gains) if gains else 0)
    avg_loss = sum(losses[-period:]) / period if len(losses) >= period else (sum(losses) / len(losses) if losses else 0)
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow:
        return closes[-1], closes[-1], 0
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    min_len = min(len(ema_fast), len(ema_slow))
    macd_line = [ema_fast[i] - ema_slow[i] for i in range(min_len)]
    signal_line = ema(macd_line, signal) if len(macd_line) >= signal else macd_line
    hist = macd_line[-1] - signal_line[-1] if signal_line else 0
    return macd_line[-1], signal_line[-1] if signal_line else 0, hist

def bollinger_bands(closes, period=20, std_dev=2):
    if len(closes) < period:
        return None, None, None
    recent = closes[-period:]
    sma_val = sum(recent) / period
    variance = sum((x - sma_val) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    return sma_val + std_dev * std, sma_val, sma_val - std_dev * std

def atr(high, low, close, period=14):
    if len(high) < period + 1:
        return None
    true_ranges = []
    for i in range(1, len(high)):
        tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
        true_ranges.append(tr)
    if len(true_ranges) < period:
        return None
    return sum(true_ranges[-period:]) / period

def obv(closes, volumes):
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
    if len(closes) < period + 1:
        return 50
    rsi_vals = []
    for i in range(period, len(closes)):
        rsi_vals.append(rsi(closes[:i+1], period))
    if len(rsi_vals) < period:
        return 50
    recent = rsi_vals[-period:]
    min_rsi = min(recent)
    max_rsi = max(recent)
    if max_rsi == min_rsi:
        return 50
    return (recent[-1] - min_rsi) / (max_rsi - min_rsi) * 100

def cci(high, low, close, period=20):
    if len(close) < period:
        return 0
    tp = [(high[i] + low[i] + close[i]) / 3 for i in range(len(close))]
    sma_tp = sum(tp[-period:]) / period
    mad = sum(abs(tp[i] - sma_tp) for i in range(-period, 0)) / period
    if mad == 0:
        return 0
    return (tp[-1] - sma_tp) / (0.015 * mad)

def williams_r(high, low, close, period=14):
    if len(close) < period:
        return -50
    highest_high = max(high[-period:])
    lowest_low = min(low[-period:])
    if highest_high == lowest_low:
        return -50
    return (highest_high - close[-1]) / (highest_high - lowest_low) * -100

def roc(closes, period=12):
    if len(closes) < period + 1:
        return 0
    prev = closes[-period-1]
    if prev == 0:
        return 0
    return (closes[-1] - prev) / prev * 100

def momentum(closes, period=10):
    if len(closes) < period + 1:
        return 0
    return closes[-1] - closes[-period-1]

def mfi(high, low, close, volume, period=14):
    if len(close) < period + 1:
        return 50
    typical_price = [(high[i] + low[i] + close[i]) / 3 for i in range(len(close))]
    money_flow = [typical_price[i] * volume[i] for i in range(len(close))]
    positive_flow, negative_flow = [], []
    for i in range(1, len(close)):
        if typical_price[i] > typical_price[i-1]:
            positive_flow.append(money_flow[i])
            negative_flow.append(0)
        else:
            positive_flow.append(0)
            negative_flow.append(money_flow[i])
    if len(positive_flow) < period:
        return 50
    pos_sum = sum(positive_flow[-period:])
    neg_sum = sum(negative_flow[-period:])
    if neg_sum == 0:
        return 100
    money_ratio = pos_sum / neg_sum
    return 100 - (100 / (1 + money_ratio))

def adx(high, low, close, period=14):
    if len(high) < period + 1:
        return None
    tr = []
    plus_dm = []
    minus_dm = []
    for i in range(1, len(high)):
        tr.append(max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])))
        up_move = high[i] - high[i-1]
        down_move = low[i-1] - low[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
    if len(tr) < period:
        return None
    atr_val = sum(tr[-period:]) / period
    if atr_val == 0:
        return None
    plus_di = 100 * (sum(plus_dm[-period:]) / period) / atr_val
    minus_di = 100 * (sum(minus_dm[-period:]) / period) / atr_val
    di_sum = plus_di + minus_di
    if di_sum == 0:
        return 0
    dx = 100 * abs(plus_di - minus_di) / di_sum
    return dx

def supertrend(high, low, close, period=10, multiplier=3):
    if len(high) < period + 1:
        return "NEUTRAL"
    atr_vals = []
    for i in range(1, len(high)):
        tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
        atr_vals.append(tr)
    if len(atr_vals) < period:
        return "NEUTRAL"
    atr_val = sum(atr_vals[-period:]) / period
    hl2 = (high[-1] + low[-1]) / 2
    lower_band = hl2 - multiplier * atr_val
    return "BUY" if close[-1] > lower_band else "SELL"

def ichimoku(high, low, close):
    if len(high) < 52:
        return "NEUTRAL"
    tenkan_high = max(high[-9:])
    tenkan_low = min(low[-9:])
    tenkan = (tenkan_high + tenkan_low) / 2
    kijun_high = max(high[-26:])
    kijun_low = min(low[-26:])
    kijun = (kijun_high + kijun_low) / 2
    senkou_a = (tenkan + kijun) / 2
    return "BUY" if close[-1] > senkou_a else "SELL"

def parabolic_sar(high, low, step=0.02, max_step=0.2):
    if len(high) < 2:
        return "NEUTRAL"
    up_trend = True
    sar = low[0]
    ep = high[0]
    af = step
    for i in range(1, len(high)):
        if up_trend:
            sar = sar + af * (ep - sar)
            if sar > low[i]:
                up_trend = False
                sar = ep
                af = step
                ep = low[i]
            else:
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + step, max_step)
        else:
            sar = sar + af * (ep - sar)
            if sar < high[i]:
                up_trend = True
                sar = ep
                af = step
                ep = high[i]
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + step, max_step)
    return "BUY" if up_trend else "SELL"

def keltner_channel(high, low, close, period=20, multiplier=2):
    if len(close) < period:
        return None, None, None
    ema_val = ema(close, period)[-1]
    atr_val = atr(high, low, close, period)
    if atr_val is None:
        return None, None, None
    return ema_val + multiplier * atr_val, ema_val, ema_val - multiplier * atr_val

def donchian_channel(high, low, period=20):
    if len(high) < period:
        return None, None
    return max(high[-period:]), min(low[-period:])

def aroon(high, low, period=25):
    if len(high) < period:
        return 50, 50
    highest_idx = np.argmax(high[-period:])
    lowest_idx = np.argmin(low[-period:])
    aroon_up = ((period - highest_idx) / period) * 100
    aroon_down = ((period - lowest_idx) / period) * 100
    return aroon_up, aroon_down

def ultimate_oscillator(high, low, close, period1=7, period2=14, period3=28):
    if len(close) < period3 + 1:
        return 50
    bp = []
    tr = []
    for i in range(1, len(close)):
        bp.append(close[i] - min(low[i], close[i-1]))
        tr.append(max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])))
    sum_tr1 = sum(tr[-period1:]) if tr else 1
    sum_tr2 = sum(tr[-period2:]) if tr else 1
    sum_tr3 = sum(tr[-period3:]) if tr else 1
    avg1 = sum(bp[-period1:]) / sum_tr1 if sum_tr1 > 0 else 0
    avg2 = sum(bp[-period2:]) / sum_tr2 if sum_tr2 > 0 else 0
    avg3 = sum(bp[-period3:]) / sum_tr3 if sum_tr3 > 0 else 0
    return ((4 * avg1) + (2 * avg2) + avg3) / 7 * 100

def cmf(high, low, close, volume, period=20):
    if len(close) < period:
        return 0
    mfv = []
    for i in range(len(close)):
        if high[i] == low[i]:
            mf = 0
        else:
            mf = ((close[i] - low[i]) - (high[i] - close[i])) / (high[i] - low[i])
        mfv.append(mf * volume[i])
    sum_mfv = sum(mfv[-period:])
    sum_vol = sum(volume[-period:])
    return sum_mfv / sum_vol if sum_vol > 0 else 0

def ease_of_movement(high, low, volume, period=14):
    if len(high) < period + 1:
        return 0
    emv = []
    for i in range(1, len(high)):
        distance = ((high[i] + low[i]) / 2) - ((high[i-1] + low[i-1]) / 2)
        box_ratio = (volume[i] / 100000000) / ((high[i] - low[i]) + 0.0001)
        if box_ratio != 0:
            emv.append(distance / box_ratio)
    if len(emv) < period:
        return 0
    return sum(emv[-period:]) / period

def std_deviation(closes, period=20):
    if len(closes) < period:
        return 0
    recent = closes[-period:]
    mean = sum(recent) / period
    variance = sum((x - mean) ** 2 for x in recent) / period
    return math.sqrt(variance)

def vwap(candles):
    total_typical = 0
    total_volume = 0
    for c in candles:
        typical = (c['high'] + c['low'] + c['close']) / 3
        total_typical += typical * c['volume']
        total_volume += c['volume']
    return total_typical / total_volume if total_volume > 0 else 0

def get_signal(buy_cond, sell_cond):
    if buy_cond:
        return 'BUY'
    if sell_cond:
        return 'SELL'
    return 'NEUTRAL'

# ========== MAIN PROCESSING ==========

def parse_candles(data):
    """Parse Yahoo Finance JSON format into rows"""
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
    """Process a single ticker"""
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
    
    # Calculate indicators (with error handling as in your original code)
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
        ema20 = ema(closes, 20)[-1] if len(closes) >= 20 else latest_close
    except:
        ema20 = latest_close
    
    try:
        ema50 = ema(closes, 50)[-1] if len(closes) >= 50 else latest_close
    except:
        ema50 = latest_close
    
    try:
        ema100 = ema(closes, 100)[-1] if len(closes) >= 100 else latest_close
    except:
        ema100 = latest_close
    
    try:
        ema200 = ema(closes, 200)[-1] if len(closes) >= 200 else latest_close
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
    
    output = {
        'symbol': ticker,
        'updated_at': pd.Timestamp.now().isoformat(),
        'latest_price': round(latest_close, 2),
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
    
    print(f"  ✅ Saved {ticker} - Close: ₹{round(latest_close, 2)}, RSI: {round(rsi_val, 2)}")
    return True

# ========== MAIN EXECUTION ==========

def main():
    print("📈 Fetching ticker list from GitHub...")
    tickers = get_available_tickers()
    
    if not tickers:
        print("❌ Could not fetch ticker list. Trying fallback mode...")
        # Fallback: try common Nifty 50 stocks
        fallback_tickers = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 
                           'HINDUNILVR', 'SBIN', 'BHARTIARTL', 'KOTAKBANK', 'ITC']
        tickers = fallback_tickers
        print(f"Using fallback ticker list: {', '.join(tickers)}")
    
    print(f"Found {len(tickers)} tickers to process")
    
    successful = 0
    for i, ticker in enumerate(tickers, 1):
        print(f"\n[{i}/{len(tickers)}]", end=" ")
        if process_ticker(ticker):
            successful += 1
    
    print(f"\n✅ Done! Processed {successful}/{len(tickers)} tickers successfully")
    print(f"📁 Results saved to {PROCESSED_DIR}/")

if __name__ == "__main__":
    main()
