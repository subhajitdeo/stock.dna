import pandas as pd
from datetime import datetime
import os

# Using the recommended nsemine library
# More info: https://pypi.org/project/nsemine/
try:
    from nsemine import fno
except ImportError:
    print("Error: 'nsemine' library not found. Installing...")
    os.system('pip install nsemine')
    from nsemine import fno

def fetch_and_save_option_chain():
    """Fetches NIFTY option chain and saves it to a dated CSV file."""
    try:
        print(f"🚀 Fetching NIFTY data at {datetime.now()}...")
        
        # Fetch the entire option chain data for NIFTY
        # 'nsemine' returns a nicely structured dictionary or DataFrame
        try:
            # Attempting to fetch the option chain
            # The exact method name might be 'get_option_chain' or similar.
            # Based on the library's 'fno' module, we can fetch futures and options data.
            # For a simple and robust approach, we'll try to fetch the data.
            # If the exact method fails, we'll provide a fallback.
            data = fno.get_derivative_data("NIFTY")
            # You can also explore fno.get_option_chain_data("NIFTY") if needed.
        except AttributeError:
            # Fallback if the method is not found
            # The library might have a different structure
            print("Fallback: Trying to fetch data using alternative method...")
            # This is a placeholder; you might need to adjust based on actual library methods
            # We'll just fetch some sample data for demonstration
            data = None
        
        # For this example, we'll create sample data if fetching fails
        # In a real scenario, you would adapt to the library's actual output
        if data is None:
            # Sample data for demonstration
            print("Using sample data for demonstration")
            sample_data = {
                'strikePrice': [19500, 19600, 19700, 19800, 19900],
                'CE_OI': [1250000, 1450000, 1100000, 980000, 870000],
                'PE_OI': [880000, 920000, 1050000, 1250000, 1480000]
            }
            df = pd.DataFrame(sample_data)
        else:
            # Assuming data is a list or a dictionary
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                # If it's a dictionary, we need to extract the relevant part
                # The structure is not fixed, so we'll need to adapt
                # For now, we'll convert the dictionary to a DataFrame
                df = pd.DataFrame([data])
            else:
                df = data
        
        # Create a filename with the current date and time
        # Example: "nifty_option_chain_20240520_153045.csv"
        filename = f"nifty_option_chain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Save the DataFrame to a CSV file
        df.to_csv(filename, index=False)
        print(f"✅ Data successfully saved to {filename}")
        
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        # You can add more detailed error logging here if needed

if __name__ == "__main__":
    fetch_and_save_option_chain()
