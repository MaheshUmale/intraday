# Trading Logic Explained

This document details the "Intelligence Framework" of the trading bot, explaining how it makes decisions. The philosophy is **Context dictates Tactics**. The bot first understands the market environment and then deploys a specific strategy tailored to that environment.

---

## **1. The Macro Framework: Day Type Classification**

Before any trade is considered, the bot classifies the "Day Type". This is the highest-level filter and determines which tactical template to use.

### **1.1 The Hunter Zone**

-   **Definition**: The High and Low of the **final 60 minutes (14:30 - 15:30)** of the previous trading day.
-   **Purpose**: This zone represents the "fair value" area where institutions were most active before the market close. It acts as a crucial support and resistance zone for the current day.
-   **Calculation (`calculate_hunter_zone` in `main.py`)**: The bot fetches the last 10 days of 1-minute candle data, programmatically finds the most recent trading day, and then isolates the last 60 minutes to find the high and low.

### **1.2 The Put-Call Ratio (PCR)**

-   **Definition**: The ratio of total open interest in Put options versus Call options.
-   **Purpose**: PCR is a sentiment indicator.
    -   **High PCR (> 1.2)**: Suggests bearish sentiment is overcrowded, often a contrarian bullish signal.
    -   **Low PCR (< 0.7)**: Suggests bullish sentiment is overcrowded, often a contrarian bearish signal.
-   **Calculation (`calculate_pcr` in `strategy.py`)**: It fetches the entire option chain for the instrument and divides the sum of all put open interest by the sum of all call open interest.

### **1.3 The Five Day Types**

The classification happens at the start of the trading day in `execute_strategy` by calling `classify_day_type` (`strategy.py`).

1.  **Bullish Trend**: `Opening Price > Hunter Zone High` AND `PCR > 1.2`.
    -   *Logic*: The market has gapped up, and the sentiment is contrarian bullish. High probability of a trend day.
    -   *Strategy Used*: `P2PTrend`.
2.  **Bearish Trend**: `Opening Price < Hunter Zone Low` AND `PCR < 0.7`.
    -   *Logic*: The market has gapped down, and sentiment is contrarian bearish.
    -   *Strategy Used*: `P2PTrend`.
3.  **Sideways Bull Trap**: `Opening Price > Hunter Zone High` AND `PCR < 0.9`.
    -   *Logic*: The market gapped up, but the underlying sentiment is bearish. This suggests the gap up is a "trap" to lure in buyers before a reversal.
    -   *Strategy Used*: `HunterTrade`.
4.  **Sideways Bear Trap**: `Opening Price < Hunter Zone Low` AND `PCR > 1.1`.
    -   *Logic*: The market gapped down, but sentiment is bullish. A potential "bear trap" before a reversal.
    -   *Strategy Used*: `HunterTrade`.
5.  **Sideways/Choppy**: The opening price is within the Hunter Zone.
    -   *Logic*: The market has not shown a clear directional bias. It's likely to be range-bound.
    -   *Strategy Used*: `MeanReversion`.

---

## **2. The Core Engine: Microstructure & Volume Analysis**

Once the Day Type is set, the bot analyzes each 1-minute candle to find an entry.

### **2.1 Microstructure Confluence Score (+/- 12)**

This is the "brain" of the bot, calculated in `calculate_microstructure_score` (`strategy.py`). It measures momentum across multiple timeframes using Elastic Volume Weighted Moving Averages (EVWMA).

-   **EVWMA (`calculate_evwma`)**: A moving average where the price is weighted by volume. It's more responsive to price moves that are accompanied by significant volume. The bot calculates this for both 1-minute and 5-minute timeframes.

-   **The Score Components**:
    -   **`dyn5` (+/- 5 pts)**: Is the current `price` above or below the `5m EVWMA`? Measures the medium-term trend.
    -   **`evm5` (+/- 5 pts)**: Is the `slope` of the `5m EVWMA` positive or negative? Measures the medium-term momentum.
    -   **`dyn1` (+/- 1 pt)**: Is the current `price` above or below the `1m EVWMA`? Measures the short-term trend.
    -   **`evm1` (+/- 1 pt)**: Is the `slope` of the `1m EVWMA` positive or negative? Measures the short-term momentum.

-   **Entry Threshold**: A trade is only considered if the absolute score is **7 or higher**. This ensures all components are in reasonable confluence.

### **2.2 VPA: The Institutional Filter**

If `USE_ADVANCED_VOLUME_ANALYSIS` is enabled in the config, a Volume Price Analysis (VPA) signal is required to confirm the Microstructure Score.

-   **For Bullish Trades (Score > 7)**: The trade needs one of the following signals:
    -   **Pocket Pivot Volume (PPV)**: The volume of the current up-bar is higher than the highest down-bar's volume in the last 10 bars. Shows strong buying pressure.
    -   **Accumulation**: Unusually high volume on a narrow-range candle that closes up. Indicates institutions are buying without moving the price significantly.
-   **For Bearish Trades (Score < -7)**: The trade needs one of the following signals:
    -   **Pivot Negative Volume (PNV)**: The volume of the current down-bar is higher than the highest up-bar's volume in the last 10 bars. Shows strong selling pressure.
    -   **Distribution**: Unusually high volume on a narrow-range candle that closes down.

If the VPA signals do not align, the trade is skipped, filtering out weak moves.

---

## **3. Tactical Templates & Risk Management**

### **3.1 `HunterTrade` (For Traps)**

-   **Entry**:
    -   Triggered on a Bull/Bear Trap day type.
    -   Waits for a Microstructure Score `>= 7` (for bull trap reversal to downside) or `<= -7` (for bear trap reversal to upside).
    -   Calculates a `probability_score` based on PCR alignment and score force. Must be `> 75`.
    -   If all conditions are met, it buys an At-The-Money (ATM) Put (for a bull trap) or Call (for a bear trap).
-   **Exit**:
    -   The `HunterTrade` does **not** have its own exit logic. It relies entirely on the global stop-loss mechanism.
    -   The exit is triggered by the `monitor_stop_loss` function in `main.py`, which checks every single incoming tick against the calculated stop-loss price.

### **3.2 `P2PTrend` (For Trends)**

-   **Entry**:
    -   Triggered on a Bullish/Bearish Trend day type.
    -   Enters on a score of `>= 7` (bullish) or `<= -7` (bearish).
    -   Buys an ATM Call (bullish) or Put (bearish).
-   **Exit**:
    -   The primary exit condition is a **reversal in the Microstructure Score**.
    -   If the bot is in a bullish position and the score flips to negative, it closes the trade.
    -   If it's in a bearish position and the score flips positive, it closes the trade.
    -   It is also protected by the global tick-level stop-loss.

### **3.3 `MeanReversion` (For Choppy Days)**

-   **Entry**:
    -   Triggered on a Sideways/Choppy day type.
    -   It does **not** use the Microstructure Score for entry.
    -   Instead, it enters when the price stretches too far from the "mean" (the 5-minute EVWMA).
    -   Enters a bearish trade (buys a Put) if `price > evwma_5m * 1.01` (1% above).
    -   Enters a bullish trade (buys a Call) if `price < evwma_5m * 0.99` (1% below).
-   **Exit**:
    -   The exit condition is the price reverting back to the mean.
    -   It closes the position if the price touches the 1-minute EVWMA.
    -   It is also protected by the global tick-level stop-loss.

### **3.4 Dynamic Stop-Loss (`calculate_stop_loss` in `strategy.py`)**

-   **Philosophy**: Fixed-point or percentage-based stop-losses are arbitrary. The bot uses a dynamic stop-loss based on **volatility and market structure**.
-   **Calculation**:
    1.  **Find Recent Swing**: It identifies the most recent swing low (for a bull trade) or swing high (for a bear trade) in the last 20 candles. This is the "structural" point.
    2.  **Calculate ATR**: It calculates the Average True Range (ATR), a measure of volatility.
    3.  **Set Stop-Loss**: The stop-loss is placed just beyond the swing point, buffered by a multiple of the ATR.
        -   `Stop = Recent Swing - (ATR * Multiplier)`
    -   The `Multiplier` is adjusted based on the strategy (`Hunter` = 1.2, `P2P Trend` = 1.5), allowing trend trades more room to breathe.
-   **Execution**: A Good Till Triggered (GTT) order is placed immediately after the entry order is filled, ensuring the stop-loss is always in the market. The position is also monitored tick-by-tick for an immediate exit if the GTT has a delay.
