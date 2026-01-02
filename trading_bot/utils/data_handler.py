import logging
import time
import upstox_client
from upstox_client.rest import ApiException
from datetime import datetime
import json
import os
import pandas as pd
import requests
import gzip
import io
import  json 
import upstox_client
from upstox_client.rest import ApiException
from upstox_client import MarketDataStreamerV3, ApiClient, Configuration

class DataHandler:
    """
    Handles data fetching from the Upstox API.
    """
    def __init__(self, api_client):
        """
        Initializes the DataHandler.
        """
        self.api_client = api_client
        self.market_data_streamer = None
        self.expiry_dates = {}
        self.instrument_mapping = {}  # To store the full mapping
        self.instrument_keys = self.getNiftyAndBNFnOKeys(api_client)


        
    def get_upstox_instruments(self, symbols=["NIFTY", "BANKNIFTY"], spot_prices={"NIFTY": 0, "BANKNIFTY": 0}):
        instrument_file = 'nse_instruments.json'

        # 1. Load Instrument Master (from local cache or download with cache invalidation)

        should_download = True
        if os.path.exists(instrument_file):
            # Check if the file is more than 24 hours old
            file_mod_time = os.path.getmtime(instrument_file)
            if (time.time() - file_mod_time) / 3600 < 24:
                print("Loading instruments from local cache (less than 24 hours old)...")
                df = pd.read_json(instrument_file)
                should_download = False
            else:
                print("Instrument cache is older than 24 hours. Re-downloading...")

        if should_download:
            print("Downloading instrument master...")
            # Download and Load Instrument Master (NSE_FO for Futures and Options)
            url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
            response = requests.get(url)
            with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as f:
                df = pd.read_json(f)

            # Save to local cache for future use
            df.to_json(instrument_file)
            print(f"Saved instrument master to {instrument_file}")

        full_mapping = {}

        for symbol in symbols:
            spot = spot_prices.get(symbol)
            
            # --- 1. Current Month Future ---
            fut_df = df[(df['name'] == symbol) & (df['instrument_type'] == 'FUT')].sort_values(by='expiry')
            current_fut_key = fut_df.iloc[0]['instrument_key']

            # --- 2. Nearest Expiry Options ---
            # Filter for Options for the specific index
            opt_df = df[(df['name'] == symbol) & (df['instrument_type'].isin(['CE', 'PE']))].copy()
            
            # Ensure expiry is in datetime format for accurate sorting
            opt_df['expiry'] = pd.to_datetime(opt_df['expiry'], origin='unix', unit='ms')
            nearest_expiry = opt_df['expiry'].min()
            near_opt_df = opt_df[opt_df['expiry'] == nearest_expiry]

            # --- 3. Identify the 7 Strikes (3 OTM, 1 ATM, 3 ITM) ---
            unique_strikes = sorted(near_opt_df['strike_price'].unique())
            
            # Find ATM strike
            atm_strike = min(unique_strikes, key=lambda x: abs(x - spot))
            atm_index = unique_strikes.index(atm_strike)
            
            # Slice range: Index - 3 to Index + 3 (Total 7 strikes)
            start_idx = max(0, atm_index - 3)
            end_idx = min(len(unique_strikes), atm_index + 4)
            selected_strikes = unique_strikes[start_idx : end_idx]

            # --- 4. Build Result ---
            option_keys = []
            for strike in selected_strikes:
                ce_key = near_opt_df[(near_opt_df['strike_price'] == strike) & (near_opt_df['instrument_type'] == 'CE')]['instrument_key'].values[0]
                ce_trading_symbol = near_opt_df[(near_opt_df['strike_price'] == strike) & (near_opt_df['instrument_type'] == 'CE')]['trading_symbol'].values[0] 
                
                pe_key = near_opt_df[(near_opt_df['strike_price'] == strike) & (near_opt_df['instrument_type'] == 'PE')]['instrument_key'].values[0]
                pe_trading_symbol = near_opt_df[(near_opt_df['strike_price'] == strike) & (near_opt_df['instrument_type'] == 'PE')]['trading_symbol'].values[0] 
                option_keys.append({
                    "strike": strike,
                    "ce": ce_key,
                    "ce_trading_symbol" :ce_trading_symbol,
                    "pe": pe_key,
                    "pe_trading_symbol" : pe_trading_symbol
                })

            full_mapping[symbol] = {
                "future": current_fut_key,
                "expiry": nearest_expiry.strftime('%Y-%m-%d'),
                "options": option_keys,
                "all_keys": [current_fut_key] + [opt['ce'] for opt in option_keys] + [opt['pe'] for opt in option_keys]
            }

        return full_mapping

    def _load_instrument_keys(self):
        """
        Loads the instrument keys from a JSON file.
        """
        try:
            with open('instrument_keys.json', 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logging.warning("instrument_keys.json not found or invalid. Instrument lookups will fail.")
            return {}

    def getNiftyAndBNFnOKeys(self, apiclient):
        """
        Retrieves the instrument keys for Nifty and Bank Nifty futures and options.
        This is a placeholder for a more dynamic instrument discovery mechanism.
        """
        # This should be a dynamic lookup in a real system.
        # For now, we'll subscribe to the main indices.


        
        ALL_FNO=[] 
        apiInstance = upstox_client.MarketQuoteV3Api(apiclient)
        try:
            # For a single instrument
            response = apiInstance.get_ltp(instrument_key="NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank")
            # print(response.data.get("NSE_INDEX|Nifty 50").get("last_price"))
            # If you want to access a specific index's last price:
            nifty_bank_data = response.data['NSE_INDEX:Nifty Bank']
            nifty_bank_last_price = nifty_bank_data.last_price  # Use dot notation here
            
            nifty_50_data = response.data['NSE_INDEX:Nifty 50']
            nifty_50_last_price = nifty_50_data.last_price    # Use dot notation here

            print(f"Nifty Bank last price: {nifty_bank_last_price}")
            print(f"Nifty 50 last price: {nifty_50_last_price}")
            
            # --- Execution ---
            # Replace spot prices with actual live LTP before running
            current_spots = {
                "NIFTY": nifty_50_last_price,
                "BANKNIFTY": nifty_bank_last_price
            }

            self.instrument_mapping = self.get_upstox_instruments(["NIFTY", "BANKNIFTY"], current_spots)
            
            self.expiry_dates['NIFTY'] = self.instrument_mapping['NIFTY']['expiry']
            self.expiry_dates['BANKNIFTY'] = self.instrument_mapping['BANKNIFTY']['expiry']

            ALL_FNO.extend(self.instrument_mapping['NIFTY']['all_keys'])
            ALL_FNO.extend(self.instrument_mapping['BANKNIFTY']['all_keys'])

            return ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"] + ALL_FNO
        except ApiException as e:
            logging.error(f"Exception when calling MarketQuoteV3Api->get_ltp: {e}")
            return ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"]

    def get_historical_candle_data(self, instrument_key:str, interval_unit:str, interval_value:str, to_date:str, from_date:str):
        """
        Fetches historical candle data, choosing the correct API endpoint based on the instrument type.
        """
        print(f"{instrument_key}, {interval_unit}, {interval_value}, {to_date}, {from_date}")
        try:
            history_api = upstox_client.HistoryV3Api(self.api_client)

            if instrument_key.startswith('NSE_EQ'):
                # The equity history API does not support a 'from_date' range.
                api_response = history_api.get_historical_candle_data(
                    instrument_key=instrument_key,
                    interval=interval_value,
                    unit=interval_unit,
                    to_date=to_date
                )
                logging.info(f"Fetched equity historical data for {instrument_key}")
            else:
                api_response = history_api.get_historical_candle_data1(instrument_key, "minutes", "1", "2026-01-02", "2026-01-01" )
                logging.info(f"Fetched F&O historical data for {instrument_key}")

            return api_response.data.candles
        except ApiException as e:
            logging.error(f"Exception when calling HistoryV3Api for {instrument_key}: {e}")
            return None

    def get_intra_day_candle_data(self, instrument_key, interval_unit, interval_value):
        """
        Fetches intraday candle data.
        """
        try:
            history_api = upstox_client.HistoryV3Api(self.api_client)
            api_response = history_api.get_intra_day_candle_data(
                instrument_key,
                interval_unit,
                interval_value
            )
            logging.info(f"Fetched intraday data for {instrument_key}")
            return api_response.data.candles
        except ApiException as e:
            logging.error(f"Exception when calling HistoryV3Api->get_intra_day_candle_data: {e}")
            return None

    def get_option_chain(self, instrument_key, expiry_date):
        """
        Fetches the option chain for a given instrument and expiry date.
        """
        try:
            options_api = upstox_client.OptionsApi(self.api_client)
            api_response = options_api.get_put_call_option_chain(instrument_key, expiry_date)
            return api_response.data
        except ApiException as e:
            logging.error(f"Exception when calling OptionsApi->get_put_call_option_chain: {e}")
            return []

    def on_auto_reconnect_stopped(self, data):
        """Handler for when auto-reconnect retries are exhausted."""
        print(f" {datetime.now()} == Auto-reconnect stopped after retries: {data}")
        # Consider manual intervention or a higher-level retry here

    def _on_open(self, *args, **kwargs):
        """Callback for when the websocket connection is opened."""
        logging.info("Websocket connection opened.")

    def _on_close(self, *args, **kwargs):
        """Callback for when the websocket connection is closed."""
        logging.info(f"Websocket connection closed.")

    def _on_error(self, *args, **kwargs):
        """Callback for websocket errors."""
        logging.error(f"Websocket error: {args}")

    def start_market_data_stream(self, instrument_keys, on_message, on_open=None, on_close=None, on_error=None):
        """
        Starts the market data WebSocket stream.
        """
        if self.market_data_streamer:
            logging.warning("Market data stream is already running.")
            return

        try:
            print("DEBUG: Initializing Streamer...", flush=True)
            self.market_data_streamer =  MarketDataStreamerV3(self.api_client, list(instrument_keys), "full")
 
            print("DEBUG: Streamer Initialized.", flush=True)
            
            # Register Callbacks
            self.market_data_streamer.on("message", on_message)
            self.market_data_streamer.on("open", on_open if on_open else self._on_open)
            self.market_data_streamer.on("error", on_error if on_error else self._on_error)
            self.market_data_streamer.on("close", on_close if on_close else self._on_close)
            
            self.market_data_streamer.on("autoReconnectStopped", self.on_auto_reconnect_stopped)
            
            # Configure Auto-Reconnect
            ENABLE_AUTO_RECONNECT = True
            INTERVAL_SECONDS = 5
            MAX_RETRIES = 5

            self.market_data_streamer.auto_reconnect(ENABLE_AUTO_RECONNECT, INTERVAL_SECONDS, MAX_RETRIES)

            time.sleep(1)
            self.market_data_streamer.connect()
            logging.info("Market data stream started.")
        except ApiException as e:
            logging.error(f"Exception when starting market data stream: {e}")
            self.market_data_streamer = None

    def stop_market_data_stream(self):
        """
        Stops the market data WebSocket stream.
        """
        if self.market_data_streamer:
            self.market_data_streamer.disconnect()
            self.market_data_streamer = None
            logging.info("Market data stream stopped.")





 