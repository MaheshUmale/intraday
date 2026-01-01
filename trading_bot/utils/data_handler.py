import upstox_client
from upstox_client.rest import ApiException
import time
import logging
import pandas as pd
import requests
import gzip
import io

class DataHandler:
    def __init__(self, api_client):
        self.api_client = api_client
        self.history_api = upstox_client.HistoryV3Api(self.api_client)
        self.options_api = upstox_client.OptionsApi(self.api_client)
        self.market_quote_api = upstox_client.MarketQuoteV3Api(self.api_client)
        self.market_holidays_and_timings_api = upstox_client.MarketHolidaysAndTimingsApi(self.api_client)
        self.market_data_streamer = None

    def get_historical_candle_data(self, instrument_key, unit, interval, to_date, from_date):
        """
        Fetches historical candle data from the Upstox API V3.
        """
        try:
            api_response = self.history_api.get_historical_candle_data1(instrument_key, unit, interval, to_date, from_date)
            return api_response.data.candles
        except ApiException as e:
            logging.error(f"Exception when calling HistoryV3Api->get_historical_candle_data1: {e}", exc_info=True)
            return None

    def get_intra_day_candle_data(self, instrument_key, unit, interval):
        """
        Fetches intra-day candle data from the Upstox API V3.
        """
        try:
            api_response = self.history_api.get_intra_day_candle_data(instrument_key, unit, interval)
            return api_response.data.candles
        except ApiException as e:
            logging.error(f"Exception when calling HistoryV3Api->get_intra_day_candle_data: {e}", exc_info=True)
            return None

    def get_option_chain(self, instrument_key, expiry_date):
        """
        Fetches the option chain for a given instrument and expiry date.
        """
        try:
            api_response = self.options_api.get_pc_option_chain(instrument_key, expiry_date)
            return api_response.data
        except ApiException as e:
            logging.error(f"Exception when calling OptionsApi->get_pc_option_chain: {e}", exc_info=True)
            return None

    def get_ltp(self, instrument_key):
        """
        Fetches the Last Traded Price (LTP) for a given instrument.
        """
        try:
            api_response = self.market_quote_api.get_ltp(instrument_key)
            return api_response.data
        except ApiException as e:
            logging.error(f"Exception when calling MarketQuoteApi->get_ltp: {e}", exc_info=True)
            return None

    def get_market_status(self, exchange):
        """
        Fetches the market status for a given exchange.
        """
        try:
            api_response = self.market_holidays_and_timings_api.get_market_status(exchange)
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

    def get_upstox_instruments(self, symbols=["NIFTY", "BANKNIFTY"], spot_prices={"NIFTY": 0, "BANKNIFTY": 0}):
        # 1. Download and Load Instrument Master (NSE_FO for Futures and Options)
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        response = requests.get(url)
        with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as f:
            df = pd.read_json(f)

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

    def getNiftyAndBNFnOKeys(self):
        ALL_FNO = []
        try:
            # Fetch LTP for Nifty 50 and Nifty Bank in a single call
            response = self.get_ltp(instrument_key="NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank")

            nifty_50_last_price = response['NSE_INDEX:Nifty 50'].last_price
            nifty_bank_last_price = response['NSE_INDEX:Nifty Bank'].last_price

            logging.info(f"Nifty 50 last price: {nifty_50_last_price}")
            logging.info(f"Nifty Bank last price: {nifty_bank_last_price}")

            # --- Execution ---
            # Replace spot prices with actual live LTP before running
            current_spots = {
                "NIFTY": nifty_50_last_price,
                "BANKNIFTY": nifty_bank_last_price
            }

            data = self.get_upstox_instruments(["NIFTY", "BANKNIFTY"], current_spots)

            logging.info(f"NIFTY Fut: {data['NIFTY']['future']}")
            logging.info(f"Total NIFTY keys to subscribe: {len(data['NIFTY']['all_keys'])}")

            ALL_FNO = ALL_FNO + data['NIFTY']['all_keys'] + data['BANKNIFTY']['all_keys']
            logging.info(ALL_FNO)
            return ALL_FNO
        except ApiException as e:
            logging.error("Exception when calling MarketQuoteV3Api->get_ltp: %s\n" % e)
            return None
