import json
import pandas as pd
from datetime import datetime
from nsepython import nse_optionchain_scrapper

def fetch_and_save_option_chain():
    try:
        print(f"🚀 Fetching NIFTY live data at {datetime.now()}...")

        # Fetch option chain
        option_chain = nse_optionchain_scrapper("NIFTY")

        # Save raw JSON
        with open("nifty_option_chain.json", "w") as f:
            json.dump(option_chain, f, indent=4)

        # Convert CE/PE data into dataframe
        records = []

        for item in option_chain["records"]["data"]:
            strike = item.get("strikePrice")

            ce = item.get("CE", {})
            pe = item.get("PE", {})

            records.append({
                "strikePrice": strike,

                "CE_OI": ce.get("openInterest"),
                "CE_Change_OI": ce.get("changeinOpenInterest"),
                "CE_LTP": ce.get("lastPrice"),
                "CE_IV": ce.get("impliedVolatility"),

                "PE_OI": pe.get("openInterest"),
                "PE_Change_OI": pe.get("changeinOpenInterest"),
                "PE_LTP": pe.get("lastPrice"),
                "PE_IV": pe.get("impliedVolatility"),
            })

        df = pd.DataFrame(records)

        # Save CSV
        df.to_csv("nifty_option_chain.csv", index=False)

        print("✅ Option chain data saved successfully!")

    except Exception as e:
        print(f"❌ An error occurred: {e}")
        raise


if __name__ == "__main__":
    fetch_and_save_option_chain()
