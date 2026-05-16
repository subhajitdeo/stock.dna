import requests
import pandas as pd
import time
from datetime import datetime

def fetch_nifty_option_chain():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.nseindia.com/',
    })
    try:
        session.get('https://www.nseindia.com', timeout=10)
        time.sleep(1)
        api_url = 'https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY'
        response = session.get(api_url, timeout=10)
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")
        data = response.json()
        records = data.get('records', {})
        spot = records.get('underlyingValue')
        calls, puts = [], []
        for item in records.get('data', []):
            strike = item.get('strikePrice')
            if 'CE' in item:
                ce = item['CE']
                calls.append({'strikePrice': strike, 'lastPrice': ce.get('lastPrice'), 'openInterest': ce.get('openInterest'), 'volume': ce.get('totalTradedVolume')})
            if 'PE' in item:
                pe = item['PE']
                puts.append({'strikePrice': strike, 'lastPrice': pe.get('lastPrice'), 'openInterest': pe.get('openInterest'), 'volume': pe.get('totalTradedVolume')})
        calls_df = pd.DataFrame(calls)
        puts_df = pd.DataFrame(puts)
        return calls_df, puts_df, spot
    except Exception as e:
        print(f"Error: {e}")
        return None, None, None

def main():
    calls, puts, spot = fetch_nifty_option_chain()
    if calls is not None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        calls.to_csv(f'nifty_calls_{timestamp}.csv', index=False)
        puts.to_csv(f'nifty_puts_{timestamp}.csv', index=False)
        print(f"Saved data. Spot: {spot}")
    else:
        print("Failed to fetch")

if __name__ == "__main__":
    main()
