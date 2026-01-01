import logging
import upstox_client
from upstox_client.rest import ApiException
from datetime import datetime
import json
import os

class DataHandler:
    """
    Handles data fetching from the Upstox API.
    """
    def __init__(self, api_client):
        """
        Initializes the DataHandler.
        """
        self.api_client = api_client
        self.api_version = "v2"
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


    def get_historical_candle_data(self, instrument_key, interval, time_unit, to_date, from_date):
        """
        Fetches historical candle data.
        """
        try:
            history_api = upstox_client.HistoryApi(self.api_client)
            api_response = history_api.get_historical_candle_data(
                instrument_key,
                interval,
                to_date,
                from_date,
                self.api_version
            )
            logging.info(f"Fetched historical data for {instrument_key}")
            return api_response.data.candles
        except ApiException as e:
            logging.error(f"Exception when calling HistoryApi->get_historical_candle_data: {e}")
            return None

    def get_intra_day_candle_data(self, instrument_key, interval):
        """
        Fetches intraday candle data.
        """
        try:
            history_api = upstox_client.HistoryApi(self.api_client)
            api_response = history_api.get_intra_day_candle_data(
                instrument_key,
                interval,
                self.api_version
            )
            logging.info(f"Fetched intraday data for {instrument_key}")
            return api_response.data.candles
        except ApiException as e:
            logging.error(f"Exception when calling HistoryApi->get_intra_day_candle_data: {e}")
            return None

    def get_option_chain(self, instrument_key, expiry_date):
        """
        Fetches the option chain for a given instrument and expiry date.
        """
        try:
            market_quote_api = upstox_client.MarketQuoteApi(self.api_client)
            api_response = market_quote_api.get_market_quote_ohlc(
                self.api_version,
                instrument_key,
                "1d" # Interval doesn't matter much for option chain
            )

            # This is a simplified representation. The actual API might require more complex parsing.
            # The SDK does not have a direct option chain method, so this is a workaround.
            # In a real system, you would parse the full market data to build the chain.
            if api_response and api_response.data:
                # Placeholder logic to simulate an option chain
                atm_strike = int(round(api_response.data.ohlc.close / 50) * 50)
                option_chain = []
                for i in range(-5, 6):
                    strike = atm_strike + i * 50
                    option_chain.append({
                        "strike_price": strike,
                        "call_options": {"instrument_key": f"NSE_FO|NIFTY{expiry_date.replace('-', '')}{strike}CE"},
                        "put_options": {"instrument_key": f"NSE_FO|NIFTY{expiry_date.replace('-', '')}{strike}PE"}
                    })
                return option_chain
            return []
        except ApiException as e:
            logging.error(f"Exception when calling MarketQuoteApi->get_market_quote_ohlc for option chain: {e}")
            return []

    def start_market_data_stream(self, instrument_keys, on_message, on_open=None, on_close=None, on_error=None):
        """
        Starts the market data WebSocket stream.
        """
        if self.market_data_streamer:
            logging.warning("Market data stream is already running.")
            return

        try:
            market_streamer_api = upstox_client.WebsocketApi(self.api_client)
            self.market_data_streamer = market_streamer_api.get_market_data_feed(
                self.api_version,
                "full", # "ltpc" for lite, "full" for full data
                ",".join(instrument_keys)
            )

            self.market_data_streamer.on_message = on_message
            if on_open: self.market_data_streamer.on_open = on_open
            if on_close: self.market_data_streamer.on_close = on_close
            if on_error: self.market_data_streamer.on_error = on_error

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
