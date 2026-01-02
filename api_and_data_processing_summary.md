# API and Data Processing Summary

This document provides a comprehensive, line-by-line summary of how the trading bot interacts with the Upstox API and processes market data.

---

## **1. Authentication (`trading_bot/authentication/auth.py`)**

The authentication process is straightforward, relying on a pre-generated access token.

-   **`UpstoxAuthenticator` Class**:
    -   **`__init__(self)`**: Initializes the authenticator. It retrieves the `UPSTOX_ACCESS_TOKEN` from the environment variables. If the token is not found, it raises an error, preventing the bot from starting without proper credentials.
    -   **`get_api_client(self)`**: This is the core method. It creates an `ApiClient` instance, sets the `Authorization` header using the access token, and returns the configured client. This client object is then used for all subsequent API calls.

---

## **2. Main Application Flow (`trading_bot/main.py`)**

The `main.py` script orchestrates the entire bot's lifecycle, from initialization to shutdown.

-   **`TradingBot` Class**:
    -   **`__init__(self, ...)`**: Initializes the bot's state, including placeholders for the API client, data handler, and order manager. It also sets up dictionaries to manage open positions and aggregate one-minute candles.
    -   **`run(self)`**: The main entry point. It follows a clear sequence:
        1.  Calls `_authenticate()` to get the API client.
        2.  Calls `_initialize_modules()` to set up the data handler and order manager.
        3.  Enters the `_trading_loop()`.
    -   **`_trading_loop(self)`**: The heart of the bot. It runs in a `while` loop, continuously checking the time.
        -   If it's within market hours (`_is_market_hours`), it ensures the WebSocket is connected. If not, it fetches all necessary F&O instrument keys using `data_handler.getNiftyAndBNFnOKeys` and starts the stream via `data_handler.start_market_data_stream`, passing the crucial `_on_message` callback.
        -   It also calls `calculate_hunter_zone` at the beginning of the session.
        -   If it's outside market hours, it disconnects the WebSocket to save resources.
    -   **`shutdown(self)`**: Gracefully stops the WebSocket connection.

---

## **3. Data Handling (`trading_bot/utils/data_handler.py`)**

This module is responsible for all data-related tasks.

-   **`DataHandler` Class**:
    -   **`getNiftyAndBNFnOKeys(self, ...)`**: This function is critical for dynamic instrument subscription.
        1.  It first uses the `MarketQuoteV3Api` to get the current live prices (LTP) of the Nifty 50 and Nifty Bank indices.
        2.  These spot prices are then fed into the `get_upstox_instruments` function.
    -   **`get_upstox_instruments(self, ...)`**:
        1.  Downloads the master list of all tradable instruments from a gzipped JSON file provided by Upstox.
        2.  For each symbol (Nifty, BankNifty), it finds the current month's future contract.
        3.  It then identifies the nearest expiry options.
        4.  Using the live spot price, it determines the At-The-Money (ATM) strike and selects 3 Out-of-The-Money (OTM) and 3 In-The-Money (ITM) strikes, for a total of 7 strikes.
        5.  It gathers the instrument keys for the future, and the call/put options for these 7 strikes, and returns them. This list is then used to subscribe to the WebSocket feed.
    -   **`get_historical_candle_data(self, ...)`**: A wrapper around the `HistoryV3Api` to fetch historical OHLCV data for a specified instrument and date range. This is primarily used by `calculate_hunter_zone`.
    -   **`start_market_data_stream(self, ...)`**:
        1.  Initializes the `MarketDataStreamerV3` with the list of instrument keys.
        2.  Assigns the callback functions (`on_message`, `on_open`, `on_error`, etc.). The `_on_message` function from `main.py` is the most important one.
        3.  Configures and enables auto-reconnection.
        4.  Calls `.connect()` to start listening for data.

---

## **4. Real-time Data Processing (`trading_bot/main.py`)**

The processing of live data happens in the `_on_message` callback function.

-   **`_on_message(self, message)`**: This function is called for every single tick received from the WebSocket.
    1.  **Protobuf Decoding**: The incoming `message` is a binary Protobuf. The `decode_protobuf` helper function parses this binary string into a structured `FeedResponse` object. This object is then converted to a Python dictionary using `MessageToDict` for easier handling.
    2.  **Data Extraction**: The code navigates the nested dictionary to extract the instrument key, price (`ltp`), and the volume of that specific trade (`ltq`).
    3.  **Live Stop-Loss Monitoring**: It immediately checks if the received tick's instrument is in the `open_positions` dictionary. If so, it calls `monitor_stop_loss` to check if the price has breached the stop-loss level.
    4.  **1-Minute Candle Aggregation**: This is a critical step.
        -   It gets the current minute (`now.replace(second=0, microsecond=0)`).
        -   If this is the first tick for an instrument, it creates a new candle dictionary, initializing the `open`, `high`, `low`, and `close` to the current price, and `volume` to the tick's volume (`ltq`).
        -   If a candle for the current minute already exists, it updates the `high` (if the price is higher), `low` (if the price is lower), `close` (always the latest price), and *increments* the `volume` with the tick's volume.
        -   If the tick's minute is *after* the timestamp of the current candle, it means a minute has just completed. The bot then:
            a.  Sends the completed candle to the `execute_strategy` function for analysis.
            b.  Creates a fresh new candle for the new minute, starting the process over.

---

## **5. Pre-computation and Context (`trading_bot/main.py`)**

Before the market opens and strategies are executed, the bot calculates the necessary context.

-   **`calculate_hunter_zone(self, ...)`**:
    1.  To be robust against holidays and weekends, it fetches data for the last 10 days.
    2.  It uses `pandas` to programmatically find the most recent trading day within that dataset.
    3.  It filters the data for that specific day and further filters it for the last 60 minutes (from 14:30 onwards).
    4.  The highest `high` and lowest `low` of this final 60-minute window are stored in the `self.hunter_zone` dictionary, which is then used for the Day Type Classification.

-   **`execute_strategy(self, ...)`**: Before executing a trade, this function gathers additional required data:
    -   It calls `data_handler.get_option_chain` to fetch the latest Open Interest data.
    -   It passes this data to `calculate_pcr` (`strategy.py`) to get the Put-Call Ratio.
    -   This PCR value, along with the pre-calculated Hunter Zone, is used to classify the day type, forming the final piece of the data processing puzzle before a trading decision is made.
