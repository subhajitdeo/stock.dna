import requests, zipfile, io, pandas as pd
from datetime import datetime

# --- Configuration ---
date_obj = datetime.now()
# Uncomment the line below to test with a known good date (e.g., a past Thursday)
# date_obj = datetime(2026, 5, 14) 

url = f"https://archives.nseindia.com/content/fo/fo{date_obj.strftime('14-05-2026')}.zip"
print(f"Attempting to download: {url}")

resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})

# --- Check if the file exists (not just a 200 OK) ---
if resp.status_code == 200 and resp.headers.get('content-type', '').startswith('application/zip'):
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            # The CSV file name is dynamic, so we just grab the first one.
            csv_file_name = z.namelist()[0]
            with z.open(csv_file_name) as csv_file:
                df = pd.read_csv(csv_file)
                df.to_csv("nifty_fo_data.csv", index=False)
                print("✅ File successfully saved as 'nifty_fo_data.csv'.")
    except zipfile.BadZipFile:
        print("❌ Error: The downloaded file is not a valid zip file.")
else:
    # This will be the case on weekends and holidays
    print(f"❌ No bhavcopy file available for {date_obj.strftime('2025-05-14')}. (Markets are likely closed)")
    print(f"   Status code: {resp.status_code}, Content-Type: {resp.headers.get('content-type')}")
    # If you want to see what was returned, uncomment the next line:
    # print(resp.text[:500]) 
