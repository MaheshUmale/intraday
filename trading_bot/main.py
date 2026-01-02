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
from google.protobuf.json_format import MessageToDict
from upstox_client.feeder.proto import MarketDataFeedV3_pb2 as MarketFeed_pb2

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

def decode_protobuf(buffer):
    """Decodes a Protobuf message."""
    feed = MarketFeed_pb2.FeedResponse()
    feed.ParseFromString(buffer)
    return feed

class TradingBot:
    """
    The main class for the trading bot.
    """
    def __init__(self):
        """
        Initializes the TradingBot.
        """
        self.api_client = None
        self.data_handler = None
        self.order_manager = None
        self.hunter_zone = {}
        self.strategies = {}
        self.open_positions = {}
        self.one_minute_candles = {}
        self.last_known_volume = {}

    def _on_message(self, message):
        """
        Callback function to handle incoming market data.
        """
        data = None
        if isinstance(message, dict):
            data = message
        elif isinstance(message, bytes):
            try:
                decoded_data = decode_protobuf(message)
                data = MessageToDict(decoded_data)
            except Exception as e:
                logging.error(f"Protobuf decode failed: {e}")
                return

        if not data or 'feeds' not in data:
            return

        for instrument_key, feed in data.get('feeds', {}).items():
            if 'marketFF' in feed.get('ff', {}):
                ltpc_data = feed['ff']['marketFF'].get('ltpc')
                if ltpc_data:
                    price = ltpc_data.get('ltp')
                    volume_change = ltpc_data.get('ltq')

                    logging.info(f"Received data for {instrument_key}: Price={price}, Volume Change={volume_change}")

                    # Live Stop-Loss Monitoring
                    if instrument_key in self.open_positions:
                        self.monitor_stop_loss(instrument_key, self.open_positions[instrument_key], price)

                    # Candle Aggregation
                    now = datetime.now()
                    current_minute = now.replace(second=0, microsecond=0)

                    if instrument_key not in self.one_minute_candles:
                        self.one_minute_candles[instrument_key] = {
                            'timestamp': current_minute,
                            'open': price,
                            'high': price,
                            'low': price,
                            'close': price,
                            'volume': volume_change
                        }
                    else:
                        candle = self.one_minute_candles[instrument_key]
                        if current_minute > candle['timestamp']:
                            self.execute_strategy(instrument_key, pd.DataFrame([candle]))
                            self.one_minute_candles[instrument_key] = {
                                'timestamp': current_minute,
                                'open': price,
                                'high': price,
                                'low': price,
                                'close': price,
                                'volume': volume_change
                            }
                        else:
                            candle['high'] = max(candle['high'], price)
                            candle['low'] = min(candle['low'], price)
                            candle['close'] = price
                            candle['volume'] += volume_change


    def run(self):
        """
        Main function to run the trading bot.
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
        Initializes the data handler and order manager.
        """
        self.data_handler = DataHandler(self.api_client)
        self.order_manager = OrderManager(self.api_client)
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
        The main trading loop.
        """
        logging.info("Entering main trading loop...")
        while True:
            now = datetime.now()
            if self._is_market_hours(now):
                if not self.data_handler.market_data_streamer:
                    if config.PAPER_TRADING:
                        self.open_positions = self.order_manager.get_paper_positions()
                    instrument_keys = self.data_handler.getNiftyAndBNFnOKeys()
                    self.data_handler.start_market_data_stream(instrument_keys, on_message=self._on_message)
                    self.calculate_hunter_zone(now)
            else:
                if self.data_handler.market_data_streamer:
                    self.data_handler.stop_market_data_stream()
            time.sleep(1)

    def _is_market_hours(self, now):
        """
        Checks if the current time is within market hours.
        """
        return dt_time(9, 15) <= now.time() <= dt_time(15, 30)

    def monitor_stop_loss(self, instrument_key, position, current_price):
        """
        Monitors the stop-loss for a given position.
        """
        stop_loss_price = position['stop_loss_price']
        if (position['direction'] == 'BULL' and current_price <= stop_loss_price) or \
           (position['direction'] == 'BEAR' and current_price >= stop_loss_price):
            logging.info(f"Stop-loss triggered for {instrument_key} at {current_price}. Closing position.")
            trade_logger.info(f"EXIT: Stop-loss, {instrument_key}, {position['transaction_type']}, {current_price}")
            self.order_manager.place_order(
                quantity=1, product="I", validity="DAY", price=0,
                instrument_token=position['instrument_key'], order_type="MARKET",
                transaction_type="SELL", tag="stop_loss_exit"
            )
            self.order_manager.close_paper_position(position['instrument_key'])
            del self.open_positions[instrument_key]

    def calculate_hunter_zone(self, current_datetime):
        """
        Calculates the Hunter Zone for each instrument.
        """
        logging.info("Calculating Hunter Zone...")
        for instrument_key in config.INSTRUMENTS:
            for i in range(1, 10):
                to_date = (current_datetime - timedelta(days=i)).strftime('%Y-%m-%d')
                from_date = (current_datetime - timedelta(days=i+1)).strftime('%Y-%m-%d')
                try:
                    candles = self.data_handler.get_historical_candle_data(instrument_key, 'minute', '1', to_date, from_date)
                    if candles:
                        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
                        break
                except Exception as e:
                    logging.error(f"Failed to fetch historical data: {e}", exc_info=True)
            if 'df' in locals() and df is not None:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                last_day_data = df[df['timestamp'].dt.date == pd.to_datetime(to_date).date()]
                last_60_min_data = last_day_data[last_day_data['timestamp'].dt.time >= dt_time(14, 30)]
                if not last_60_min_data.empty:
                    self.hunter_zone[instrument_key] = {
                        'high': last_60_min_data['high'].max(),
                        'low': last_60_min_data['low'].min()
                    }
                    logging.info(f"Hunter Zone for {instrument_key}: {self.hunter_zone[instrument_key]}")

    def execute_strategy(self, instrument_key, df):
        """
        Executes the trading strategy for a given instrument.
        """
        logging.info(f"Executing strategy for {instrument_key}...")
        if instrument_key in self.open_positions:
            logging.info(f"Position already open for {instrument_key}. Skipping.")
            return
        if instrument_key not in self.hunter_zone:
            logging.warning(f"Hunter Zone not available for {instrument_key}. Skipping.")
            return
        hunter_zone = self.hunter_zone[instrument_key]
        opening_price = df['open'].iloc[0]
        option_chain = self.data_handler.get_option_chain(instrument_key, datetime.now().strftime('%Y-%m-%d'))
        if not option_chain:
            logging.warning(f"Could not fetch option chain for {instrument_key}. Skipping.")
            return
        pcr = calculate_pcr(option_chain)
        day_type = classify_day_type(opening_price, hunter_zone['high'], hunter_zone['low'], pcr)
        df_1m = calculate_evwma(df.copy(), length=20)
        evwma_1m = df_1m['evwma'].iloc[-1]
        evwma_1m_slope = df_1m['evwma_slope'].iloc[-1]
        df_5m = df.resample('5T', on='timestamp').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
        df_5m = calculate_evwma(df_5m, length=20)
        evwma_5m = df_5m['evwma'].iloc[-1]
        evwma_5m_slope = df_5m['evwma_slope'].iloc[-1]
        price = df['close'].iloc[-1]
        score = calculate_microstructure_score(price, evwma_1m, evwma_5m, evwma_1m_slope, evwma_5m_slope)
        logging.info(f"Instrument: {instrument_key}, Day Type: {day_type.value}, Score: {score}")
        if config.USE_ADVANCED_VOLUME_ANALYSIS:
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
                evwma_1m=evwma_1m, evwma_5m=evwma_5m, df=df
            )

    def shutdown(self):
        """
        Gracefully shuts down the trading bot.
        """
        logging.info("Shutting down the trading bot...")
        if self.data_handler:
            self.data_handler.stop_market_data_stream()
        logging.info("Trading bot has been shut down.")


if __name__ == "__main__":
    bot = TradingBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        bot.shutdown()
