import time
import logging
from datetime import datetime, timedelta, time as dt_time
import pandas as pd
from trading_bot.authentication.auth import UpstoxAuthenticator
from trading_bot.utils.data_handler import DataHandler
from trading_bot.execution.execution import OrderManager
from trading_bot.strategy.strategy import (
    classify_day_type, calculate_microstructure_score, calculate_pcr,
    calculate_evwma, HunterTrade, P2PTrend, Scalp, MeanReversion, DayType,
    detect_pocket_pivot_volume, detect_pivot_negative_volume,
    detect_accumulation, detect_distribution
)
import trading_bot.config as config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Create a dedicated logger for trades
trade_logger = logging.getLogger('trade_logger')
trade_logger.setLevel(logging.INFO)
fh = logging.FileHandler('trades.log')
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
fh.setFormatter(formatter)
trade_logger.addHandler(fh)

class TradingBot:
    """
    The main class for the algorithmic trading bot.

    This class orchestrates the entire trading process, including authentication,
    data fetching, strategy execution, and order management.
    """
    def __init__(self, config_override=None):
        """
        Initializes the TradingBot.

        Args:
            config_override (module, optional): A configuration module to override
                                                the default settings. Defaults to None.
        """
        self.config = config_override if config_override else config
        self.api_client = None
        self.data_handler = None
        self.order_manager = None
        self.hunter_zone = {}  # Stores high/low of the last 60 mins of the previous day
        self.strategies = {}  # Maps day types to their corresponding trading strategies
        self.open_positions = {}  # Tracks currently open positions
        self.last_processed_timestamp = {}  # Prevents processing the same candle multiple times
        self.latest_volume_cache = {}  # Caches the latest volume for futures contracts


    def run(self):
        """
        The main entry point to start the trading bot.

        This method handles the main execution loop, including authentication,
        module initialization, and the primary trading loop.
        """
        logging.info("Starting the trading bot...")
        try:
            self._authenticate()
            self._initialize_modules()
            self._trading_loop()
        except Exception as e:
            logging.error(f"An unexpected error occurred in the main run loop: {e}", exc_info=True)

    def _authenticate(self):
        """
        Authenticates with the Upstox API.
        """
        authenticator = UpstoxAuthenticator()
        self.api_client = authenticator.get_api_client()
        if not self.api_client:
            logging.error("Authentication failed. Exiting.")
            raise ConnectionError("Failed to authenticate with Upstox API.")
        logging.info("Authentication successful.")

    def _initialize_modules(self):
        """
        Initializes and wires up the necessary components of the bot.
        """
        self.data_handler = DataHandler(self.api_client)
        self.order_manager = OrderManager(self.api_client)

        # Map each classified day type to a specific trading strategy instance.
        # This allows the bot to dynamically select the correct tactical template.
        self.strategies = {
            DayType.BULLISH_TREND: P2PTrend(self.order_manager),
            DayType.BEARISH_TREND: P2PTrend(self.order_manager),
            DayType.SIDEWAYS_BULL_TRAP: HunterTrade(self.order_manager),
            DayType.SIDEWAYS_BEAR_TRAP: HunterTrade(self.order_manager),
            DayType.SIDEWAYS_CHOPPY: MeanReversion(self.order_manager)
        }
        logging.info("Modules initialized.")

    def _trading_loop(self):
        """
        The main polling loop that runs continuously during market hours.

        This loop fetches the full list of instruments, calculates the initial
        Hunter Zone, and then enters a per-minute loop to fetch and process
        the latest candle data.
        """
        logging.info("Entering main trading loop...")

        instrument_keys = self.data_handler.getNiftyAndBNFnOKeys(self.api_client)
        self.config.INSTRUMENTS.clear()
        self.config.INSTRUMENTS.extend(instrument_keys)
        self.calculate_hunter_zone(datetime.now())

        if self.config.PAPER_TRADING:
            self.open_positions = self.order_manager.get_paper_positions()

        while True:
            now = datetime.now()
            if self._is_market_hours(now):
                self.fetch_and_process_candles()

            # Sleep until the next minute
            next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            sleep_duration = (next_minute - now).total_seconds()
            try:
                time.sleep(sleep_duration)
            except KeyboardInterrupt:
                logging.info("Trading loop interrupted. Shutting down.")
                break

    def fetch_and_process_candles(self):
        """
        Called every minute to fetch the latest candle for each instrument,
        prevent duplicate processing, and trigger strategy execution.
        """
        for instrument_key in self.config.INSTRUMENTS:
            try:
                # Fetches the full intraday history for the instrument.
                candles = self.data_handler.get_intra_day_candle_data(instrument_key, 'minutes', '1')
                if not candles:
                    continue

                # The last candle in the list is the most recent one.
                latest_candle = candles[-1]
                candle_timestamp = datetime.fromisoformat(latest_candle['timestamp'])
                
                # Prevent reprocessing the same candle in subsequent ticks.
                if self.last_processed_timestamp.get(instrument_key) == candle_timestamp:
                    continue

                self.last_processed_timestamp[instrument_key] = candle_timestamp

                # Cache the latest volume for potential use in spot index calculations.
                self.latest_volume_cache[instrument_key] = latest_candle.get('volume', 0)

                # Convert the full history of candles to a DataFrame for indicator calculations.
                df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                self.execute_strategy(instrument_key, df, candle_timestamp)

            except Exception as e:
                logging.error(f"Error processing candles for {instrument_key}: {e}", exc_info=True)


    def _is_market_hours(self, now):
        """
        Checks if the current time is within the configured market hours.

        Args:
            now (datetime): The current datetime.

        Returns:
            bool: True if within market hours, False otherwise.
        """
        return dt_time(9, 15) <= now.time() <= dt_time(15, 30)

    def monitor_stop_loss(self, instrument_key, position, current_price, timestamp):
        """
        Monitors and executes the stop-loss for a given open position.

        Args:
            instrument_key (str): The instrument key of the position.
            position (dict): The dictionary containing position details.
            current_price (float): The current market price of the instrument.
            timestamp (datetime): The current timestamp for logging.
        """
        stop_loss_price = position['stop_loss_price']

        # Check if the stop-loss is triggered based on the direction of the trade.
        if (position['direction'] == 'BULL' and current_price <= stop_loss_price) or \
           (position['direction'] == 'BEAR' and current_price >= stop_loss_price):

            logging.info(f"Stop-loss triggered for {instrument_key} at {current_price}. Closing position.")
            trade_logger.info(f"EXIT: Stop-loss, {instrument_key}, {position['transaction_type']}, {current_price}")

            # Place the exit order (works for both live and paper trading via OrderManager).
            self.order_manager.place_order(
                quantity=1, product="I", validity="DAY", price=0,
                instrument_token=position['instrument_key'], order_type="MARKET",
                transaction_type="SELL", tag="stop_loss_exit",
                timestamp=timestamp
            )

            # Remove the position from the open positions tracker.
            del self.open_positions[instrument_key]

    def calculate_hunter_zone(self, current_datetime):
        """
        Calculates the "Hunter Zone" for all tracked instruments.

        The Hunter Zone is defined as the high and low of the last 60 minutes
        of the previous trading day. This zone is a key input for classifying
        the current day's market type.

        Args:
            current_datetime (datetime): The current datetime, used to determine
                                         the date range for fetching historical data.
        """
        logging.info("Calculating Hunter Zone...")
        to_date = current_datetime.strftime('%Y-%m-%d')
        from_date = (current_datetime - timedelta(days=10)).strftime('%Y-%m-%d')

        for instrument_key in self.config.INSTRUMENTS:
            try:
                # Fetch data for the last 10 days to ensure we get the last trading day
                candles = self.data_handler.get_historical_candle_data(
                    instrument_key, 'minutes', '1', to_date, from_date
                )

                if not candles:
                    logging.warning(f"No historical data found for {instrument_key} in the last 10 days.")
                    continue

                # Create DataFrame and process timestamps
                df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])

                # Find the most recent trading day from the data
                last_trading_day = df['timestamp'].dt.date.max()
                if pd.isna(last_trading_day):
                    logging.warning(f"Could not determine the last trading day for {instrument_key}.")
                    continue

                # Filter data for the last trading day
                last_day_data = df[df['timestamp'].dt.date == last_trading_day]

                # Filter for the last 60 minutes of that day (14:30 onwards)
                last_60_min_data = last_day_data[last_day_data['timestamp'].dt.time >= dt_time(14, 30)]

                if not last_60_min_data.empty:
                    self.hunter_zone[instrument_key] = {
                        'high': last_60_min_data['high'].max(),
                        'low': last_60_min_data['low'].min()
                    }
                    logging.info(f"Hunter Zone for {instrument_key} on {last_trading_day}: {self.hunter_zone[instrument_key]}")
                else:
                    logging.warning(f"No data found in the last 60 minutes for {instrument_key} on {last_trading_day}.")

            except Exception as e:
                logging.error(f"Failed to calculate Hunter Zone for {instrument_key}: {e}", exc_info=True)

    def execute_strategy(self, instrument_key, df, timestamp, option_chain=None):
        """
        Executes the trading strategy for a given instrument.
        Can accept a pre-fetched option_chain to avoid redundant API calls.
        """
        if df.empty:
            return

        logging.info(f"Executing strategy for {instrument_key}...")
        if instrument_key in self.open_positions:
            logging.info(f"Position already open for {instrument_key}. Skipping.")
            return
        if instrument_key not in self.hunter_zone:
            logging.warning(f"Hunter Zone not available for {instrument_key}. Skipping.")
            return
        hunter_zone = self.hunter_zone[instrument_key]
        opening_price = df['open'].iloc[0]

        symbol = None
        # Efficiently look up the symbol for the given instrument key.
        if instrument_key.startswith('NSE_FO'):
            # Use the pre-computed inverted map for O(1) lookup.
            symbol = self.data_handler.instrument_to_symbol_map.get(instrument_key)
        else:
            # For indices, derive the symbol from the key itself.
            if 'BANKNIFTY' in instrument_key or 'Nifty Bank' in instrument_key:
                symbol = 'BANKNIFTY'
            elif 'NIFTY' in instrument_key or 'Nifty 50' in instrument_key:
                symbol = 'NIFTY'

        # For spot indices (which don't have their own volume), substitute the volume
        # from their corresponding futures contract for more accurate indicator calculations.
        if instrument_key in ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"] and df['volume'].iloc[-1] == 0:
            future_key = self.data_handler.instrument_mapping.get(symbol, {}).get('future')
            if future_key and future_key in self.latest_volume_cache:
                future_volume = self.latest_volume_cache[future_key]
                df.loc[df.index[-1], 'volume'] = future_volume
                logging.info(f"Substituted volume for {instrument_key} with future volume ({future_volume}) from {future_key}")

        if not symbol or not self.data_handler.expiry_dates.get(symbol):
            logging.warning(f"Could not determine symbol or expiry for {instrument_key}. Skipping option chain.")
            return

        expiry_date = self.data_handler.expiry_dates[symbol]

        # Determine the correct underlying instrument key for the option chain API call
        underlying_instrument = "NSE_INDEX|Nifty 50" if symbol == 'NIFTY' else "NSE_INDEX|Nifty Bank"

        if option_chain is None: # Fetch only if not provided (i.e., in live mode)
            option_chain = self.data_handler.get_option_chain(underlying_instrument, expiry_date)

        if not option_chain:
            logging.warning(f"Could not fetch option chain for {underlying_instrument} with expiry {expiry_date}. Skipping.")
            return

        pcr = calculate_pcr(option_chain)
        day_type = classify_day_type(opening_price, hunter_zone['high'], hunter_zone['low'], pcr)
        df_1m = calculate_evwma(df.copy(), length=20)
        evwma_1m = df_1m['evwma'].iloc[-1]
        evwma_1m_slope = df_1m['evwma_slope'].iloc[-1]

        # Resample to 5-minute timeframe for multi-timeframe analysis.
        df_5m = df.resample('5min', on='timestamp').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()

        df_5m = calculate_evwma(df_5m, length=20)

        # Ensure there is data in the 5-minute dataframe before accessing.
        if df_5m.empty:
            logging.warning(f"Not enough data to generate 5-minute candles for {instrument_key}. Skipping.")
            return

        evwma_5m = df_5m['evwma'].iloc[-1]
        evwma_5m_slope = df_5m['evwma_slope'].iloc[-1]
        price = df['close'].iloc[-1]
        score = calculate_microstructure_score(price, evwma_1m, evwma_5m, evwma_1m_slope, evwma_5m_slope)
        logging.info(f"Instrument: {instrument_key}, Day Type: {day_type.value}, Score: {score}")
        if self.config.USE_ADVANCED_VOLUME_ANALYSIS:
            ppv = detect_pocket_pivot_volume(df)
            pnv = detect_pivot_negative_volume(df)
            accumulation = detect_accumulation(df)
            distribution = detect_distribution(df)
            logging.info(f"VPA Signals: PPV={ppv}, PNV={pnv}, Accumulation={accumulation}, Distribution={distribution}")
            if (score > 0 and not (ppv or accumulation)) or \
               (score < 0 and not (pnv or distribution)):
                logging.info("VPA signals do not confirm the microstructure score. Skipping trade.")
                return
        strategy = self.strategies.get(day_type)
        if strategy:
            vpa_signal = None
            if config.USE_ADVANCED_VOLUME_ANALYSIS:
                if ppv: vpa_signal = "PPV"
                elif pnv: vpa_signal = "PNV"
                elif accumulation: vpa_signal = "Accumulation"
                elif distribution: vpa_signal = "Distribution"
            strategy.execute(
                score=score, price=price, vpa_signal=vpa_signal,
                instrument_key=instrument_key, hunter_zone=hunter_zone, pcr=pcr,
                day_type=day_type, option_chain=option_chain, open_positions=self.open_positions,
                evwma_1m=evwma_1m, evwma_5m=evwma_5m, df=df,
                timestamp=timestamp # Pass timestamp to strategy
            )
    
import time
import signal
import sys

# Define a clean exit handler (optional but good practice)
def signal_handler(sig, frame):
    print('\nCtrl+C received! Shutting down gracefully...')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
    bot = TradingBot()
    bot.run()