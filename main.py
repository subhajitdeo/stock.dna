import requests, zipfile, io, pandas as pd
from datetime import datetime

# Use a specific past trading day (May 14, 2026)
date_obj = datetime(2026, 5, 14)  # Thursday
url = f"https://archives.nseindia.com/content/fo/fo{date_obj.strftime('%d%m%Y')}.zip"
print(f"Fetching: {url}")

resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})

if resp.status_code == 200 and resp.headers.get('content-type', '').startswith('application/zip'):
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    df = pd.read_csv(z.open(z.namelist()[0]))
    df.to_csv("nifty_fo_data.csv", index=False)
    print("✅ Saved as 'nifty_fo_data.csv'")
else:
    print(f"❌ Failed: status {resp.status_code}, content-type: {resp.headers.get('content-type')}")
