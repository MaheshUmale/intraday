import sys
import os
import argparse
from datetime import datetime, time as dt_time
import pandas as pd

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_bot.main import TradingBot
import trading_bot.config as config


class Backtester:
    """
    Class to run a backtest of the trading strategy using historical data from the Upstox API.
    """

    def __init__(self):
        """
        Initializes the Backtester.
        """
        # Create a copy of the default config to override for the backtest
        backtest_config = config
        backtest_config.PAPER_TRADING = True
        self.trading_bot = TradingBot(config_override=backtest_config)
        print("Forcing PAPER_TRADING mode for backtest.")

    def run_backtest(self, from_date_str, to_date_str):
        """
        Runs the backtest for a given date range.
        Args:
            from_date_str (str): The start date for the backtest in 'YYYY-MM-DD' format.
            to_date_str (str): The end date for the backtest in 'YYYY-MM-DD' format.
        """
        print("--- Starting Backtest ---")
        print(f"Date Range: {from_date_str} to {to_date_str}")

        # 1. Initialize the bot
        self.trading_bot._authenticate()
        self.trading_bot._initialize_modules()

        # 2. Set the Hunter Zone for the start of the day
        start_date = datetime.strptime(from_date_str, '%Y-%m-%d')
        self.trading_bot.calculate_hunter_zone(start_date)

        # 3. Fetch all historical 1-minute candles for the date range
        all_candles = []
        for instrument_key in self.trading_bot.config.INSTRUMENTS:
            candles = self.trading_bot.data_handler.get_historical_candle_data(
                instrument_key, '1', 'minute', to_date_str, from_date_str
            )
            if candles:
                all_candles.extend([(instrument_key, candle) for candle in candles])

        # Sort all candles by timestamp chronologically
        all_candles.sort(key=lambda x: x[1]['timestamp'])

        print(f"Fetched {len(all_candles)} total candles for backtesting.")

        # 4. Iterate through each candle and execute the strategy
        for instrument_key, candle in all_candles:
            candle_timestamp = datetime.fromisoformat(candle['timestamp'])

            # Create a DataFrame for the single candle
            df = pd.DataFrame([candle], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Execute the strategy for this candle
            self.trading_bot.execute_strategy(instrument_key, df, candle_timestamp)

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
    parser = argparse.ArgumentParser(description="Run a backtest of the trading strategy.")
    parser.add_argument("--from_date", required=True, help="Start date for the backtest in 'YYYY-MM-DD' format.")
    parser.add_argument("--to_date", required=True, help="End date for the backtest in 'YYYY-MM-DD' format.")
    args = parser.parse_args()

    # --- Run Backtester ---
    backtester = Backtester()
    backtester.run_backtest(from_date_str=args.from_date, to_date_str=args.to_date)
