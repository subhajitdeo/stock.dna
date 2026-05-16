import pandas as pd
from datetime import datetime
import os

# Install and import the reliable nsefin library
try:
    from nsefin import nse
except ImportError:
    print("Installing nsefin library...")
    os.system('pip install nsefin')
    from nsefin import nse

def fetch_and_save_option_chain():
    """Fetches live NIFTY option chain and saves to a CSV file."""
    try:
        print(f"Fetching NIFTY data at {datetime.now()}...")
        
        # Use nsefin's get_option_chain method (returns a dictionary with 'CE' and 'PE')
        option_chain = nse.get_option_chain("NIFTY")
        
        if not option_chain or ('CE' not in option_chain or 'PE' not in option_chain):
            raise ValueError("No valid data returned from nse.get_option_chain")
        
        # Create DataFrames for Calls and Puts
        call_df = pd.DataFrame(option_chain['CE'])
        put_df = pd.DataFrame(option_chain['PE'])
        
        # Add identifiers
        call_df['option_type'] = 'CE'
        put_df['option_type'] = 'PE'
        
        # Combine the data
        combined_df = pd.concat([call_df, put_df], ignore_index=True)
        
        # Add a timestamp
        combined_df['fetch_timestamp'] = datetime.now().isoformat()
        
        # Save the file with a timestamp
        filename = f"nifty_option_chain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        combined_df.to_csv(filename, index=False)
        print(f"✅ Data saved to {filename} with {len(combined_df)} rows")
        
        # Save a file for the latest data
        combined_df.to_csv("nifty_option_chain_latest.csv", index=False)
        print("✅ Latest copy saved to 'nifty_option_chain_latest.csv'")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        # Log the error for debugging
        with open("error_log.txt", "a") as f:
            f.write(f"{datetime.now()}: {str(e)}\n")
        raise

if __name__ == "__main__":
    fetch_and_save_option_chain()
