import pandas as pd
from datetime import datetime
import os
import sys

# Use the nsemine library
try:
    from nsemine import nse
except ImportError:
    print("nsemine not found, installing...")
    os.system('pip install nsemine')
    from nsemine import nse

def fetch_and_save_option_chain():
    """Fetches live NIFTY option chain and saves to a CSV file."""
    try:
        print(f"🚀 Fetching NIFTY live data at {datetime.now()}...")
        
        # Fetch option chain using nsemine's nse module
        # The function returns a dictionary with keys 'CE' and 'PE'
        option_chain = nse.option_chain("NIFTY")
        
        if not option_chain:
            raise ValueError("No data returned from nse.option_chain")
        
        # Extract Call and Put DataFrames
        call_df = pd.DataFrame(option_chain['CE'])
        put_df = pd.DataFrame(option_chain['PE'])
        
        # Add a column to identify option type
        call_df['option_type'] = 'CE'
        put_df['option_type'] = 'PE'
        
        # Combine both into one DataFrame
        combined_df = pd.concat([call_df, put_df], ignore_index=True)
        
        # Add a timestamp for when the data was fetched
        combined_df['fetch_timestamp'] = datetime.now().isoformat()
        
        # Create filename with current timestamp
        filename = f"nifty_option_chain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Save to CSV
        combined_df.to_csv(filename, index=False)
        print(f"✅ Real data saved to {filename} with {len(combined_df)} rows")
        
        # Also save a latest copy (overwrite) for easy access
        combined_df.to_csv("nifty_option_chain_latest.csv", index=False)
        print("✅ Also saved as 'nifty_option_chain_latest.csv'")
        
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        # Write error to a log file for debugging
        with open("error_log.txt", "a") as f:
            f.write(f"{datetime.now()}: {str(e)}\n")
        # Re-raise so the GitHub Action shows failure
        raise

if __name__ == "__main__":
    fetch_and_save_option_chain()
