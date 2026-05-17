import json
import os
import pandas as pd
import numpy as np
import math

DATA_DIR = 'data'
PROCESSED_DIR = 'data/processed'
MIN_DAYS = 30

os.makedirs(PROCESSED_DIR, exist_ok=True)

# ========== INDICATOR CALCULATION FUNCTIONS ==========

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
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
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
    return (closes[-1] - closes[-period-1]) / closes[-period-1] * 100

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
    atr_val = sum(tr[-period:]) / period if tr else 0
    plus_di = 100 * (sum(plus_dm[-period:]) / period) / atr_val if atr_val != 0 else 0
    minus_di = 100 * (sum(minus_dm[-period:]) / period) / atr_val if atr_val != 0 else 0
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) != 0 else 0
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
    upper_band = hl2 + multiplier * atr_val
    lower_band = hl2 - multiplier * atr_val
    return "BUY" if close[-1] > lower_band else "SELL"

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

files = [f for f in os.listdir(DATA_DIR) if f.endswith('.json') and f != 'processed']
print(f'Found {len(files)} files to process')

for filename in files:
    ticker = filename.replace('.json', '')
    print(f'\n📊 Processing {ticker}...')
    
    try:
        with open(os.path.join(DATA_DIR, filename), 'r') as f:
            data = json.load(f)
        
        rows = []
        
        # Check if data is a list (array format) OR dict (Yahoo format)
        if isinstance(data, list):
            # Direct array of OHLCV objects
            rows = data
        elif isinstance(data, dict):
            # Yahoo format with 'chart' key
            result = data.get('chart', {}).get('result', [])
            if not result:
                print(f'  No data for {ticker}')
                continue
            
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
                        'open': float(o),
                        'high': float(h),
                        'low': float(l),
                        'close': float(c),
                        'volume': int(v)
                    })
        else:
            print(f'  Unknown data format for {ticker}')
            continue
        
        if len(rows) < MIN_DAYS:
            print(f'  Only {len(rows)} days, skipping')
            continue
        
        # Sort by time ascending
        rows.sort(key=lambda x: x['time'])
        
        closes = [r['close'] for r in rows]
        highs = [r['high'] for r in rows]
        lows = [r['low'] for r in rows]
        volumes = [r['volume'] for r in rows]
        latest_close = closes[-1]
        
        # Calculate indicators
        rsi_val = rsi(closes)
        macd_line, macd_sig, macd_hist = macd(closes)
        bb_upper, bb_mid, bb_lower = bollinger_bands(closes)
        atr_val = atr(highs, lows, closes)
        obv_vals = obv(closes, volumes)
        stoch_rsi_val = stochastic_rsi(closes)
        cci_val = cci(highs, lows, closes)
        williams_val = williams_r(highs, lows, closes)
        roc_val = roc(closes)
        mom_val = momentum(closes)
        mfi_val = mfi(highs, lows, closes, volumes)
        adx_val = adx(highs, lows, closes)
        supertrend_signal = supertrend(highs, lows, closes)
        vwap_val = vwap(rows)
        
        # EMAs and SMAs
        ema20 = ema(closes, 20)[-1] if len(closes) >= 20 else latest_close
        ema50 = ema(closes, 50)[-1] if len(closes) >= 50 else latest_close
        ema100 = ema(closes, 100)[-1] if len(closes) >= 100 else latest_close
        ema200 = ema(closes, 200)[-1] if len(closes) >= 200 else latest_close
        sma20 = sma(closes, 20)
        sma50 = sma(closes, 50)
        sma200 = sma(closes, 200)
        
        # Generate output
        output = {
            'symbol': ticker,
            'updated_at': pd.Timestamp.now().isoformat(),
            'latest_price': round(latest_close, 2),
            'candles': rows[-252:],
            'indicators': {
                'RSI': {'value': round(rsi_val, 2), 'signal': get_signal(rsi_val < 30, rsi_val > 70)},
                'StochasticRSI': {'value': round(stoch_rsi_val, 2), 'signal': get_signal(stoch_rsi_val < 20, stoch_rsi_val > 80)},
                'MACD': {'value': round(macd_line, 2), 'signal': get_signal(macd_line > macd_sig, macd_line < macd_sig)},
                'CCI': {'value': round(cci_val, 2), 'signal': get_signal(cci_val < -100, cci_val > 100)},
                'Williams_R': {'value': round(williams_val, 2), 'signal': get_signal(williams_val < -80, williams_val > -20)},
                'ROC': {'value': round(roc_val, 2), 'signal': get_signal(roc_val > 0, roc_val < 0)},
                'Momentum': {'value': round(mom_val, 2), 'signal': get_signal(mom_val > 0, mom_val < 0)},
                'MFI': {'value': round(mfi_val, 2), 'signal': get_signal(mfi_val < 20, mfi_val > 80)},
                'ADX': {'value': round(adx_val, 2) if adx_val else None, 'signal': 'STRONG' if adx_val and adx_val > 25 else 'WEAK'},
                'SuperTrend': {'signal': supertrend_signal},
                'EMA20': {'value': round(ema20, 2), 'signal': get_signal(latest_close > ema20, latest_close < ema20)},
                'EMA50': {'value': round(ema50, 2), 'signal': get_signal(latest_close > ema50, latest_close < ema50)},
                'EMA100': {'value': round(ema100, 2), 'signal': get_signal(latest_close > ema100, latest_close < ema100)},
                'EMA200': {'value': round(ema200, 2), 'signal': get_signal(latest_close > ema200, latest_close < ema200)},
                'SMA20': {'value': round(sma20, 2), 'signal': get_signal(latest_close > sma20, latest_close < sma20)},
                'SMA50': {'value': round(sma50, 2), 'signal': get_signal(latest_close > sma50, latest_close < sma50)},
                'SMA200': {'value': round(sma200, 2), 'signal': get_signal(latest_close > sma200, latest_close < sma200)},
                'BollingerBands': {'upper': round(bb_upper, 2) if bb_upper else None, 'middle': round(bb_mid, 2) if bb_mid else None, 'lower': round(bb_lower, 2) if bb_lower else None, 'signal': get_signal(latest_close < bb_lower, latest_close > bb_upper) if bb_lower else 'NEUTRAL'},
                'ATR': {'value': round(atr_val, 2) if atr_val else None},
                'OBV': {'value': int(obv_vals[-1]) if obv_vals else None, 'signal': get_signal(obv_vals[-1] > obv_vals[-2], obv_vals[-1] < obv_vals[-2]) if len(obv_vals) > 1 else 'NEUTRAL'},
                'VWAP': {'value': round(vwap_val, 2), 'signal': get_signal(latest_close > vwap_val, latest_close < vwap_val)}
            }
        }
        
        out_path = os.path.join(PROCESSED_DIR, ticker)
        with open(out_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f'  ✅ Saved {ticker} - RSI: {round(rsi_val, 2)}, Price: {round(latest_close, 2)}')
        
    except Exception as e:
        print(f'  ❌ Error: {e}')

print('\n✅ All indicators calculated successfully!')
