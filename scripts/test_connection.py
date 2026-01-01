import os
from dotenv import load_dotenv
import upstox_client
from upstox_client.rest import ApiException
from datetime import datetime

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))
UPSTOX_API_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

# Configure the Upstox API client
configuration = upstox_client.Configuration()
configuration.access_token = UPSTOX_API_TOKEN
api_client = upstox_client.ApiClient(configuration)

# Create an instance of the HistoryV3Api
history_api = upstox_client.HistoryV3Api(api_client)

# Define the parameters for the API call
instrument_key = "NSE_INDEX|Nifty 50"
unit = "days"
interval = "1"
to_date = datetime.now().strftime('%Y-%m-%d')
from_date = "2024-05-20"

try:
    # Make the API call with the correct parameters
    api_response = history_api.get_historical_candle_data1(instrument_key, unit, interval, to_date, from_date)
    print("API Response:")
    print(api_response)
except ApiException as e:
    print(f"Error calling Upstox API: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
