import nsefin
import pandas as pd

# Correct way to initialize the client
nse = nsefin.NSEClient()

# Fetch the NIFTY option chain
try:
    oc = nse.get_option_chain("NIFTY")
    if oc is not None and not oc.empty:
        print("Option chain fetched successfully!")
        print(oc.head())
    else:
        print("Data is empty.")
except Exception as e:
    print(f"Error fetching data: {e}")
