import upstox_client
from upstox_client.rest import ApiException
import time
import logging

class DataHandler:
    def __init__(self, api_client):
        self.api_client = api_client
        self.history_api = upstox_client.HistoryV3Api(self.api_client)
        self.options_api = upstox_client.OptionsApi(self.api_client)
        self.market_quote_api = upstox_client.MarketQuoteV3Api(self.api_client)
        self.market_holidays_and_timings_api = upstox_client.MarketHolidaysAndTimingsApi(self.api_client)
        self.market_data_streamer = None

    def get_historical_candle_data(self, instrument_key, interval, to_date, from_date):
        """
        Fetches historical candle data from the Upstox API V3.
        """
        try:
            api_response = self.history_api.get_historical_candle_data(instrument_key, interval, to_date, from_date, api_version="v3")
            return api_response.data.candles
        except ApiException as e:
            logging.error(f"Exception when calling HistoryV3Api->get_historical_candle_data: {e}", exc_info=True)
            return None

    def get_intra_day_candle_data(self, instrument_key, interval):
        """
        Fetches intra-day candle data from the Upstox API V3.
        """
        try:
            api_response = self.history_api.get_intra_day_candle_data(instrument_key, interval, api_version="v3")
            return api_response.data.candles
        except ApiException as e:
            logging.error(f"Exception when calling HistoryV3Api->get_intra_day_candle_data: {e}", exc_info=True)
            return None

    def get_option_chain(self, instrument_key, expiry_date):
        """
        Fetches the option chain for a given instrument and expiry date.
        """
        try:
            api_response = self.options_api.get_pc_option_chain("v2", instrument_key, expiry_date)
            return api_response.data
        except ApiException as e:
            logging.error(f"Exception when calling OptionsApi->get_pc_option_chain: {e}", exc_info=True)
            return None

    def get_ltp(self, instrument_key):
        """
        Fetches the Last Traded Price (LTP) for a given instrument.
        """
        try:
            api_response = self.market_quote_api.ltp(instrument_key, "v2")
            return api_response.data
        except ApiException as e:
            logging.error(f"Exception when calling MarketQuoteApi->ltp: {e}", exc_info=True)
            return None

    def get_market_status(self, exchange):
        """
        Fetches the market status for a given exchange.
        """
        try:
            api_response = self.market_holidays_and_timings_api.get_market_status("v2", exchange)
            return api_response.data
        except ApiException as e:
            logging.error(f"Exception when calling MarketHolidaysAndTimingsApi->get_market_status: {e}", exc_info=True)
            return None

    def start_market_data_stream(self, instrument_keys, mode='full', on_message=None):
        """
        Starts the WebSocket market data stream.
        """
        self.market_data_streamer = upstox_client.MarketDataStreamerV3(
            self.api_client, instrument_keys, mode
        )

        def default_on_message(message):
            logging.info(f"Received market data: {message}")

        self.market_data_streamer.on("message", on_message or default_on_message)

        def on_open():
            logging.info("Market data stream connected.")

        def on_error(error):
            logging.error(f"Market data stream error: {error}", exc_info=True)

        self.market_data_streamer.on("open", on_open)
        self.market_data_streamer.on("error", on_error)

        self.market_data_streamer.connect()

    def stop_market_data_stream(self):
        """
        Stops the WebSocket market data stream.
        """
        if self.market_data_streamer:
            self.market_data_streamer.disconnect()
            logging.info("Market data stream disconnected.")
