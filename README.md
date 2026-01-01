# Python-Based Algorithmic Trading System

This document serves as both the **Master Logic Document** and the **User Guide** for the algorithmic trading system. It is designed to provide a comprehensive understanding of the system's architecture, trading intelligence, and operational procedures.

---

## **Part 1: How to Set Up and Run the Bot**

This section provides a step-by-step guide to get the trading bot running on your local machine.

### **1.1 Prerequisites**
*   Python 3.10 or higher.
*   An active Upstox trading account.
*   API credentials from the [Upstox Developer Console](https://upstox.com/developer/).

### **1.2 Installation**

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Install Dependencies:**
    It is highly recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

### **1.3 Configuration (`.env` file)**

Create a file named `.env` in the root of the project directory. This file will store your sensitive API credentials and is ignored by Git.

Populate the `.env` file with the following content, replacing the placeholder values with your actual credentials from the Upstox Developer Console:

```plaintext
UPSTOX_API_KEY="Your_Upstox_API_Key"
UPSTOX_API_SECRET="Your_Upstox_API_Secret"
UPSTOX_REDIRECT_URI="https//127.0.0.1:5000/auth/callback" # Or your configured redirect URI
UPSTOX_ACCESS_TOKEN="" # Leave this empty initially
```

### **1.4 First-Time Authentication**

The system uses OAuth2 for secure authentication. You only need to perform this authorization step once. The application will then store and manage the access token for you.

1.  **Run the Main Application:**
    ```bash
    python -m trading_bot.main
    ```

2.  **Authorize in Browser:**
    The first time you run the bot, it will detect that there is no access token. It will print a URL in your console.
    *   Copy this URL.
    *   Paste it into your web browser.
    *   Log in with your Upstox credentials and grant the application access.

3.  **Enter the Authorization Code:**
    After granting access, you will be redirected to your `REDIRECT_URI`. The URL in your browser's address bar will now contain a parameter called `code`. It will look something like this:
    `https://127.0.0.1:5000/auth/callback?code=**<long_authorization_code>**`

    *   Copy the value of the `code` parameter.
    *   Paste this code back into the terminal where the bot is prompting for it.

The application will then automatically fetch the access token, save it to your `.env` file, and proceed with its normal operation. You will not have to do this again unless your token is revoked.

### **1.5 Running the Bot and Tests**

*   **To Run the Trading Bot:**
    ```bash
    python -m trading_bot.main
    ```

*   **To Run the Unit Tests:**
    ```bash
    python -m unittest discover -s tests
    ```

### **1.6 System Configuration (`trading_bot/config.py`)**

The `trading_bot/config.py` file allows you to control key system parameters without changing the code:

*   **PAPER_TRADING**: Set to `True` to run in paper trading mode (default). Set to `False` to execute real trades. **Use with caution.**
*   **USE_ADVANCED_VOLUME_ANALYSIS**: Set to `True` to enable the VPA signal filter. Set to `False` to rely only on the Microstructure Score.

---

## **Part 2: The Master Logic Document**

This section codifies the "Intelligence Framework" of the trading system.

### **2.1 The Logic Loop: From Data to Trade**

The system operates on a real-time, event-driven loop:

1.  **WebSocket Data Feed**: The bot establishes a WebSocket connection to the Upstox API, subscribing to live ticks for key instruments (Nifty 50, Nifty Bank).
2.  **1-Minute Candle Aggregation**: The `_on_message` handler receives each tick. It aggregates these ticks into one-minute candles, correctly calculating the `open`, `high`, `low`, `close`, and `volume` for that minute. The volume is calculated by tracking the *change* in the cumulative volume provided by the feed.
3.  **Strategy Execution Trigger**: At the close of each one-minute candle, the `execute_strategy` function is called for that instrument.
4.  **Analysis & Filtering**: The system performs a multi-layered analysis:
    *   Calculates the **Microstructure Confluence Score**.
    *   (If enabled) Detects **VPA signals** for institutional activity.
    *   Filters the trade signal based on these analytics.
5.  **Order Placement**: If a high-conviction trade setup is identified, the `OrderManager` places the order (either a paper trade or a live trade).
6.  **Live Stop-Loss Monitoring**: Every incoming tick is also used to check the price against the stop-loss levels of any open positions for real-time risk management.

### **2.2 The Macro Framework: Day Type Classification**

The foundational principle is **Context dictates Tactics**. The engine first classifies the "Regime" or **Day Type**.

*   **The Hunter Zone**: The price range (High and Low) of the **final 60 minutes of the previous trading day**. This is the reference for institutional "fair value".
*   **The Five Day Types**: Determined by the **Opening Price**, the **Hunter Zone**, and the **PCR (Put-Call Ratio)**.
    1.  **Bullish Trend**: Gap Up + High PCR.
    2.  **Bearish Trend**: Gap Down + Low PCR.
    3.  **Sideways Bull Trap**: Gap Up + Bearish PCR (a "trap").
    4.  **Sideways Bear Trap**: Gap Down + Bullish PCR (a "trap").
    5.  **Sideways/Choppy**: Opens within the previous day's range.

### **2.3 The Engine: Microstructure & Volume Analysis**

#### **2.3.1 Microstructure Confluence Score (+/- 12)**

The "brain" of the system. It uses multi-timeframe EVWMA (Elastic Volume Weighted Moving Average) analysis to generate a real-time momentum score.

*   **dyn5 (5 pts)**: Price vs. 5m EVWMA.
*   **dyn1 (1 pt)**: Price vs. 1m EVWMA.
*   **evm5 (5 pts)**: Slope of 5m EVWMA.
*   **evm1 (1 pt)**: Slope of 1m EVWMA.

A score of **+/- 7** is the minimum threshold for a high-conviction entry.

#### **2.3.2 VPA: The Institutional Filter**

If `USE_ADVANCED_VOLUME_ANALYSIS` is `True`, the system uses Volume Price Analysis to confirm the Microstructure Score. A trade is only taken if the volume signature supports the price action.

*   **For Bullish Trades (Score > 0)**: The trade requires confirmation from either:
    *   **Pocket Pivot Volume (PPV)**: High up-volume that exceeds the highest down-volume of the last 10 bars.
    *   **Accumulation**: Unusually high volume on a narrow-range bar, closing up.
*   **For Bearish Trades (Score < 0)**: The trade requires confirmation from either:
    *   **Pivot Negative Volume (PNV)**: High down-volume that exceeds the highest up-volume of the last 10 bars.
    *   **Distribution**: Unusually high volume on a narrow-range bar, closing down.

If the VPA signals do not align with the Microstructure Score, the trade is skipped, filtering out low-conviction setups.

### **2.4 Tactical Templates & Risk Management**

*   **Tactical Templates**: The system uses specific strategies based on the Day Type (e.g., `HunterTrade` for morning traps, `P2PTrend` for trending days).
*   **Dynamic Stop-Loss**: Stop-losses are calculated dynamically based on a multiple of the **ATR (Average True Range)** and placed beyond a recent **structural swing point**. This is a more robust approach than using fixed-point stops.
*   **Probability Weighting**: Before entry, every potential trade is assigned a probability score (0-100%) based on factors like PCR alignment and score force. Only trades with a score **> 75%** are considered.
