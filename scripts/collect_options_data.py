import os
import sys
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

# Add project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trading_bot.authentication.auth import UpstoxAuthenticator
from trading_bot.utils.data_handler import DataHandler

def collect_and_store_nifty_options_data(api, symbol):
    """
    Collects current Nifty options data and stores it.
    """
    print(f"Collecting options data for {symbol}")

    data_handler = DataHandler(api)

    # 1. Get the nearest expiry date for Nifty
    nifty_instrument_key = "NSE_INDEX|Nifty 50"

    data_handler.getNiftyAndBNFnOKeys(api)
    expiry_date = data_handler.expiry_dates.get(symbol)

    if not expiry_date:
        print(f"Could not determine expiry date for {symbol}. Exiting.")
        return

    print(f"Nearest expiry for {symbol} is {expiry_date}")

    # 2. Fetch the option chain
    option_chain = data_handler.get_option_chain(nifty_instrument_key, expiry_date)

    if not option_chain:
        print("Could not fetch option chain. Exiting.")
        return

    # 3. Process and store the data (including PCR calculation)
    total_ce_oi = 0
    total_pe_oi = 0

    for strike_data in option_chain:
        put_option = strike_data.put_options
        if put_option and hasattr(put_option, 'market_data') and put_option.market_data and hasattr(put_option.market_data, 'oi'):
            total_pe_oi += put_option.market_data.oi

        call_option = strike_data.call_options
        if call_option and hasattr(call_option, 'market_data') and call_option.market_data and hasattr(call_option.market_data, 'oi'):
            total_ce_oi += call_option.market_data.oi

    pcr_data = []
    if total_ce_oi > 0:
        pcr = total_pe_oi / total_ce_oi
        print(f"Total CE OI: {total_ce_oi}, Total PE OI: {total_pe_oi}, PCR: {pcr}")
        pcr_data.append({
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "pcr": pcr,
            "total_ce_oi": total_ce_oi,
            "total_pe_oi": total_pe_oi
        })
    else:
        print("Total Call OI is zero, cannot calculate PCR.")

    # 4. Store data
    if pcr_data:
        output_dir = 'data'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        filepath = os.path.join(output_dir, f"pcr_data_{symbol}.csv")
        pcr_df = pd.DataFrame(pcr_data)

        header = not os.path.exists(filepath)
        pcr_df.to_csv(filepath, mode='a', header=header, index=False)

        print(f"PCR data appended successfully to {filepath}.")
    else:
        print("No PCR data to store.")


def main():
    """
    Main function to run the data collection script.
    """
    load_dotenv()

    access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if not access_token:
        print("Error: UPSTOX_ACCESS_TOKEN environment variable not set.")
        sys.exit(1)

    authenticator = UpstoxAuthenticator()
    api_client = authenticator._configure_api_client(access_token)

    collect_and_store_nifty_options_data(api_client, "NIFTY")


if __name__ == "__main__":
    main()
