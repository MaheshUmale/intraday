import sys
import os
import pymongo
from datetime import datetime, time as dt_time

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_bot.main import TradingBot
import trading_bot.config as config


class Backtester:
    """
    Class to run a backtest of the trading strategy using historical data from MongoDB.
    """

    def __init__(self, mongo_uri, mongo_db):
        """
        Initializes the Backtester.
        Args:
            mongo_uri (str): The MongoDB connection URI.
            mongo_db (str): The name of the MongoDB database.
        """
        self.mongo_client = pymongo.MongoClient(mongo_uri)
        self.db = self.mongo_client[mongo_db]

        # Create a copy of the default config to override for the backtest
        backtest_config = config
        backtest_config.PAPER_TRADING = True
        self.trading_bot = TradingBot(config_override=backtest_config)
        print("Forcing PAPER_TRADING mode for backtest.")

    def run_backtest(self, start_date_str, end_date_str):
        """
        Runs the backtest for a given date range.
        Args:
            start_date_str (str): The start date for the backtest in 'YYYY-MM-DD' format.
            end_date_str (str): The end date for the backtest in 'YYYY-MM-DD' format.
        """
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

        # Convert dates to millisecond timestamp strings for the query
        start_ts_ms = int(start_date.timestamp() * 1000)
        end_ts_ms = int(end_date.timestamp() * 1000)

        print("--- Starting Backtest ---")
        print(f"Date Range: {start_date_str} to {end_date_str}")

        # 1. Initialize the bot
        self.trading_bot._authenticate()
        self.trading_bot._initialize_modules()

        # 2. Set the Hunter Zone for the start of the day
        # In a real scenario, this would be calculated based on the previous day's data
        self.trading_bot.calculate_hunter_zone(start_date)

        # 3. Fetch historical data from MongoDB using the correct timestamp field
        # Note: The collection name might be different, e.g., 'market_data'
        ticks_cursor = self.db.ticks.find({
            'currentTs': {
                '$gte': str(start_ts_ms),
                '$lt': str(end_ts_ms)
            }
        }).sort('currentTs', 1)

        print("Fetching and processing historical market data feeds...")

        tick_count = 0
        for doc in ticks_cursor:
            # The document itself is the message
            message = doc

            # Extract and convert the timestamp from the document
            ts_ms = int(doc['currentTs'])
            tick_timestamp = datetime.fromtimestamp(ts_ms / 1000.0)

            # 4. Simulate the WebSocket message, passing the full message and historical timestamp
            self.trading_bot._on_message(message, tick_timestamp)
            tick_count += 1

        print(f"Processed {tick_count} ticks.")
        print("--- Backtest Complete ---")

        # 5. Analyze results
        self.analyze_results()

    def analyze_results(self):
        """
        Analyzes and prints the results of the backtest.
        """
        print("\n--- Backtest Results ---")

        # Access the paper trades from the OrderManager
        paper_trades = self.trading_bot.order_manager.get_all_paper_trades()

        if not paper_trades:
            print("No trades were executed during the backtest.")
            return

        total_trades = len(paper_trades)
        winning_trades = 0
        losing_trades = 0
        total_pnl = 0

        for trade in paper_trades:
            pnl = trade['pnl']
            total_pnl += pnl
            if pnl > 0:
                winning_trades += 1
            else:
                losing_trades += 1

            print(f"Trade: {trade['instrument_key']} | Entry: {trade['entry_price']} | Exit: {trade['exit_price']} | PnL: {pnl:.2f}")

        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

        print("\n--- Summary ---")
        print(f"Total Trades: {total_trades}")
        print(f"Winning Trades: {winning_trades}")
        print(f"Losing Trades: {losing_trades}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total PnL: {total_pnl:.2f}")

if __name__ == "__main__":
    # --- Configuration ---
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB_NAME = os.environ.get("MONGO_DB", "upstox_data")
    BACKTEST_START_DATE = "2023-01-20"
    BACKTEST_END_DATE = "2023-01-21"

    # --- Run Backtester ---
    backtester = Backtester(mongo_uri=MONGO_URI, mongo_db=MONGO_DB_NAME)
    backtester.run_backtest(start_date_str=BACKTEST_START_DATE, end_date_str=BACKTEST_END_DATE)
