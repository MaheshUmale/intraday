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
    Runs a historical backtest of the trading strategy.

    This class simulates the live trading environment by iterating through historical
    candle data chronologically, feeding it to the trading bot, and tracking the
    resulting paper trades.
    """

    def __init__(self):
        """
        Initializes the Backtester, ensuring paper trading is enabled.
        """
        backtest_config = config
        backtest_config.PAPER_TRADING = True  # Force paper trading mode for safety
        self.trading_bot = TradingBot(config_override=backtest_config)
        print("Forcing PAPER_TRADING mode for backtest.")

    def run_backtest(self, from_date_str, to_date_str):
        """
        Executes the backtest over a specified date range.

        The process involves:
        1. Initializing the bot and its modules.
        2. Fetching all relevant F&O instruments.
        3. Calculating the initial Hunter Zone.
        4. Fetching all 1-minute candles for the period.
        5. Iterating through each candle chronologically to simulate a live feed.
        6. Caching option chain data to avoid API rate limiting.
        7. Executing the strategy for each candle.
        8. Analyzing and printing the results.

        Args:
            from_date_str (str): The start date for the backtest (e.g., '2023-01-01').
            to_date_str (str): The end date for the backtest (e.g., '2023-01-03').
        """
        print("--- Starting Backtest ---")
        print(f"Date Range: {from_date_str} to {to_date_str}")

        # 1. Initialize the bot
        self.trading_bot._authenticate()
        self.trading_bot._initialize_modules()

        # 2. Dynamically get all instruments first
        print("Fetching full list of F&O instruments...")
        instrument_keys = self.trading_bot.data_handler.getNiftyAndBNFnOKeys(self.trading_bot.api_client)
        self.trading_bot.config.INSTRUMENTS.clear()
        self.trading_bot.config.INSTRUMENTS.extend(instrument_keys)
        print(f"Now tracking {len(instrument_keys)} instruments.")

        # 3. Set the Hunter Zone for all instruments
        start_date = datetime.strptime(from_date_str, '%Y-%m-%d')
        self.trading_bot.calculate_hunter_zone(start_date)

        # 4. Fetch all historical 1-minute candles for the date range
        all_candles = []
        print(f"Fetching historical candle data for all instruments...")
        for instrument_key in self.trading_bot.config.INSTRUMENTS:
            try:
                # Corrected argument order: unit, interval, from_date, to_date
                candles = self.trading_bot.data_handler.get_historical_candle_data(
                    instrument_key, 'minutes', '1', from_date_str, to_date_str
                )
                if candles:
                    all_candles.extend([(instrument_key, candle) for candle in candles])
            except Exception as e:
                print(f"Could not fetch data for {instrument_key}: {e}")


        if not all_candles:
            print("No candle data fetched for the given date range. Exiting backtest.")
            return

        # Sort all candles by timestamp chronologically. The candle is a list, so we access by index.
        all_candles.sort(key=lambda x: x[1][0])

        print(f"Fetched {len(all_candles)} total candles for backtesting.")

        # 4. Iterate through each candle, simulating the passage of time
        instrument_dfs = {}  # Dictionary to store accumulating dataframes for each instrument
        option_chain_cache = {} # Cache to avoid excessive API calls
        candle_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi']

        for instrument_key, candle_list in all_candles:
            candle_timestamp = datetime.fromisoformat(candle_list[0])

            # Ignore data outside of market hours for a more realistic simulation
            if not dt_time(9, 15) <= candle_timestamp.time() <= dt_time(15, 30):
                continue

            # Create a dictionary from the list to handle data correctly
            candle_dict = dict(zip(candle_columns, candle_list))

            # Update volume cache, mimicking live behavior
            self.trading_bot.latest_volume_cache[instrument_key] = candle_dict.get('volume', 0)

            # Get or create the DataFrame for the current instrument
            if instrument_key not in instrument_dfs:
                instrument_dfs[instrument_key] = pd.DataFrame(columns=candle_columns).astype({
                    'open': 'float64', 'high': 'float64', 'low': 'float64', 'close': 'float64',
                    'volume': 'int64', 'oi': 'int64'
                })
                instrument_dfs[instrument_key]['timestamp'] = pd.to_datetime(instrument_dfs[instrument_key]['timestamp'])

            # Append the new candle data
            new_candle_df = pd.DataFrame([candle_dict])
            instrument_dfs[instrument_key] = pd.concat([instrument_dfs[instrument_key], new_candle_df], ignore_index=True)

            # Ensure timestamp column is in the correct format after concat
            instrument_dfs[instrument_key]['timestamp'] = pd.to_datetime(instrument_dfs[instrument_key]['timestamp'])

            # --- Option Chain Caching ---
            # Generate a cache key for the current minute
            cache_key = candle_timestamp.strftime('%Y-%m-%d %H:%M')

            # Fetch and cache the option chain for both Nifty and Bank Nifty if not already in cache for this minute
            if cache_key not in option_chain_cache:
                option_chain_cache[cache_key] = {}
                try:
                    nifty_expiry = self.trading_bot.data_handler.expiry_dates.get('NIFTY')
                    if nifty_expiry:
                        option_chain_cache[cache_key]['NIFTY'] = self.trading_bot.data_handler.get_option_chain(
                            "NSE_INDEX|Nifty 50", nifty_expiry
                        )
                except Exception as e:
                    print(f"Error fetching NIFTY option chain for {cache_key}: {e}")

                try:
                    bn_expiry = self.trading_bot.data_handler.expiry_dates.get('BANKNIFTY')
                    if bn_expiry:
                        option_chain_cache[cache_key]['BANKNIFTY'] = self.trading_bot.data_handler.get_option_chain(
                            "NSE_INDEX|Nifty Bank", bn_expiry
                        )
                except Exception as e:
                    print(f"Error fetching BANKNIFTY option chain for {cache_key}: {e}")


            # --- Pass Cached Data to Strategy ---
            # Use the centralized method to get the symbol for the instrument.
            symbol = self.trading_bot.get_symbol_from_instrument_key(instrument_key)

            # Get the correct option chain from the cache for the current minute.
            current_option_chain = option_chain_cache.get(cache_key, {}).get(symbol)

            # Execute the strategy with the cumulative DataFrame and the cached option chain
            self.trading_bot.execute_strategy(
                instrument_key,
                instrument_dfs[instrument_key].copy(),
                candle_timestamp,
                option_chain=current_option_chain # Pass cached data
            )

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
