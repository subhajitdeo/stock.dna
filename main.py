import requests, zipfile, io, pandas as pd
from datetime import datetime

url = f"https://archives.nseindia.com/content/fo/fo{datetime.now().strftime('%d%m%Y')}.zip"
resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
if resp.status_code == 200:
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    df = pd.read_csv(z.open(z.namelist()[0]))
    df.to_csv("nifty_fo_data.csv", index=False)
    print("Saved. Upload this CSV to GitHub.")
