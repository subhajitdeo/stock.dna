import json
import os
import pandas as pd
import numpy as np
import math

DATA_DIR = 'data'
PROCESSED_DIR = 'data/processed'
MIN_DAYS = 30

os.makedirs(PROCESSED_DIR, exist_ok=True)

def ema(values, period):
    alpha = 2 / (period + 1)
    result = [values[0]]
    for val in values[1:]:
        result.append(alpha * val + (1 - alpha) * result[-1])
    return result

def sma(values, period):
    if len(values) < period:
        return values
    result = []
    for i in range(period, len(values) + 1):
        result.append(sum(values[i-period:i]) / period)
    return result

def rsi_calc(closes, period=14):
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    
    avg_gain = sum(gains[-period:]) / period if len(gains) >= period else sum(gains) / len(gains) if gains else 0
    avg_loss = sum(losses[-period:]) / period if len(losses) >= period else sum(losses) / len(losses) if losses else 0
    
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd_calc(closes, fast=12, slow=26, signal=9):
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(ema_slow))]
    signal_line = ema(macd_line, signal)
    return macd_line[-1], signal_line[-1]

def bollinger_bands(closes, period=20, std_dev=2):
    if len(closes) < period:
        return None, None, None
    recent = closes[-period:]
    sma_val = sum(recent) / period
    variance = sum((x - sma_val) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    upper = sma_val + std_dev * std
    lower = sma_val - std_dev * std
    return upper, sma_val, lower

def atr_calc(high, low, close, period=14):
    true_ranges = []
    for i in range(1, len(high)):
        tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
        true_ranges.append(tr)
    if len(true_ranges) >= period:
        return sum(true_ranges[-period:]) / period
    return None

def obv_calc(closes, volumes):
    obv_vals = [volumes[0]]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv_vals.append(obv_vals[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            obv_vals.append(obv_vals[-1] - volumes[i])
        else:
            obv_vals.append(obv_vals[-1])
    return obv_vals

def get_signal(buy_cond, sell_cond):
    if buy_cond:
        return 'BUY'
    if sell_cond:
        return 'SELL'
    return 'NEUTRAL'

files = [f for f in os.listdir(DATA_DIR) if f.endswith('.json') and f != 'processed']
print(f'Found {len(files)} files to process')

for filename in files:
    ticker = filename.replace('.json', '')
    print(f'\nProcessing {ticker}...')
    
    try:
        with open(os.path.join(DATA_DIR, filename), 'r') as f:
            raw = json.load(f)
        
        result = raw.get('chart', {}).get('result', [])
        if not result:
            print(f'  No data for {ticker}')
            continue
        
        quotes = result[0].get('indicators', {}).get('quote', [{}])[0]
        timestamps = result[0].get('timestamp', [])
        
        rows = []
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
        
        if len(rows) < MIN_DAYS:
            print(f'  Only {len(rows)} days, skipping')
            continue
        
        closes = [row['close'] for row in rows]
        highs = [row['high'] for row in rows]
        lows = [row['low'] for row in rows]
        volumes = [row['volume'] for row in rows]
        latest_close = closes[-1]
        
        # Calculate indicators
        rsi_val = rsi_calc(closes)
        macd_line, macd_signal = macd_calc(closes)
        bb_upper, bb_mid, bb_lower = bollinger_bands(closes)
        atr_val = atr_calc(highs, lows, closes)
        obv_vals = obv_calc(closes, volumes)
        
        # EMA calculations
        ema20 = ema(closes, 20)[-1] if len(closes) >= 20 else latest_close
        ema50 = ema(closes, 50)[-1] if len(closes) >= 50 else latest_close
        sma20 = sma(closes, 20)[-1] if len(closes) >= 20 else latest_close
        
        # Signals
        rsi_signal = get_signal(rsi_val < 30, rsi_val > 70)
        macd_signal_val = get_signal(macd_line > macd_signal, macd_line < macd_signal)
        bb_signal = get_signal(latest_close < bb_lower, latest_close > bb_upper) if bb_lower else 'NEUTRAL'
        ema20_signal = get_signal(latest_close > ema20, latest_close < ema20)
        
        output = {
            'symbol': ticker,
            'updated_at': pd.Timestamp.now().isoformat(),
            'latest_price': round(latest_close, 2),
            'candles': rows[-252:],
            'indicators': {
                'RSI': {'value': round(rsi_val, 2), 'signal': rsi_signal},
                'MACD': {'value': round(macd_line, 2), 'signal': macd_signal_val},
                'EMA20': {'value': round(ema20, 2), 'signal': ema20_signal},
                'SMA20': {'value': round(sma20, 2)},
                'BollingerBands': {
                    'upper': round(bb_upper, 2) if bb_upper else None,
                    'lower': round(bb_lower, 2) if bb_lower else None,
                    'signal': bb_signal
                },
                'ATR': {'value': round(atr_val, 2) if atr_val else None},
                'OBV': {'value': int(obv_vals[-1]) if obv_vals else None}
            }
        }
        
        out_path = os.path.join(PROCESSED_DIR, ticker)
        with open(out_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f'  Saved {ticker} - RSI: {round(rsi_val, 2)}')
        
    except Exception as e:
        print(f'  Error: {e}')

print('\nDone!')
