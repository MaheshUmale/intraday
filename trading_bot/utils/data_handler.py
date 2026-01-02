import logging
import upstox_client
from upstox_client.rest import ApiException
from datetime import datetime
import json
import os

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
        self.instrument_keys = self._load_instrument_keys()

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

    def getNiftyAndBNFnOKeys(self):
        """
        Retrieves the instrument keys for Nifty and Bank Nifty futures and options.
        This is a placeholder for a more dynamic instrument discovery mechanism.
        """
        # This should be a dynamic lookup in a real system.
        # For now, we'll subscribe to the main indices.
        return ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"]

    def get_historical_candle_data(self, instrument_key, interval_unit, interval_value, to_date, from_date):
        """
        Fetches historical candle data.
        """
        try:
            history_api = upstox_client.HistoryV3Api(self.api_client)
            api_response = history_api.get_historical_candle_data1(
                instrument_key,
                interval_unit,
                interval_value,
                to_date,
                from_date
            )
            logging.info(f"Fetched historical data for {instrument_key}")
            return api_response.data.candles
        except ApiException as e:
            logging.error(f"Exception when calling HistoryV3Api->get_historical_candle_data1: {e}")
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
            api_response = options_api.get_pc_option_chain(instrument_key, expiry_date)
            return api_response.data
        except ApiException as e:
            logging.error(f"Exception when calling OptionsApi->get_pc_option_chain: {e}")
            return []

    def on_auto_reconnect_stopped(self, data):
        """Handler for when auto-reconnect retries are exhausted."""
        print(f" {datetime.now()} == Auto-reconnect stopped after retries: {data}")
        # Consider manual intervention or a higher-level retry here

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
            self.market_data_streamer.on("open", on_open if on_open else lambda: None)
            self.market_data_streamer.on("error", on_error if on_error else lambda err: None)
            self.market_data_streamer.on("close", on_close if on_close else lambda: None)
            
            self.market_data_streamer.on("autoReconnectStopped", self.on_auto_reconnect_stopped)
            
            # Configure Auto-Reconnect
            ENABLE_AUTO_RECONNECT = True
            INTERVAL_SECONDS = 5
            MAX_RETRIES = 5

            self.market_data_streamer.auto_reconnect(ENABLE_AUTO_RECONNECT, INTERVAL_SECONDS, MAX_RETRIES)

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
