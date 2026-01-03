# Detailed Analysis of Trading Logic

This document provides a detailed breakdown of each type of trade the bot can execute, as per the logic found in the source code and documentation.

---

### **Trade Type: Hunter Trade**

-   **Conditions:**
    -   The "Day Type" must be classified as either a **Sideways Bull Trap** (`Opening Price > Hunter Zone High` AND `PCR < 0.9`) or a **Sideways Bear Trap** (`Opening Price < Hunter Zone Low` AND `PCR > 1.1`).
    -   The absolute **Microstructure Confluence Score** must be `>= 7`.
    -   The calculated **Probability Score** must be `>= 75`.
    -   If enabled, a confirming **VPA Signal** (e.g., Pocket Pivot Volume, Distribution) must be present.

-   **Reasons:**
    -   This trade is designed to capitalize on **failed breakouts** and **trapped traders**.
    -   A "Bull Trap" occurs when the market gaps up, luring in buyers, but the underlying sentiment (low PCR) is bearish. The bot anticipates that this initial upward move is weak and will reverse.
    -   A "Bear Trap" is the inverse, where a gap down entices sellers, but bullish sentiment (high PCR) suggests a probable reversal to the upside.
    -   The edge comes from fading a sentiment-divergent move, entering just as the reversal momentum is confirmed by the Microstructure Score, which acts as the conviction trigger.

-   **Setup:**
    -   The market opens with a gap above the previous day's final hour high or below its low.
    -   The Put-Call Ratio (PCR) indicates that the underlying market sentiment is opposite to the direction of the gap.
    -   The bot waits for the initial momentum to exhaust and for the price action to show signs of reversal.

-   **Entry:**
    -   The trigger is a **Microstructure Confluence Score of +/- 7 or greater**, indicating that momentum across multiple timeframes is now aligned with the anticipated reversal.
    -   For a Bull Trap, the bot waits for the score to become strongly negative (`<= -7`) and then buys an **At-The-Money (ATM) Put Option**.
    -   For a Bear Trap, the bot waits for the score to become strongly positive (`>= 7`) and then buys an **At-The-Money (ATM) Call Option**.

-   **SL (Stop-Loss):**
    -   The Stop-Loss is **dynamic and based on market structure and volatility**.
    -   It is calculated by finding the most recent swing high (for a short trade) or swing low (for a long trade) within the last 20 candles.
    -   A buffer is added to this swing point, calculated as `1.2 * ATR (Average True Range)`.
    -   A Good Till Triggered (GTT) order for the stop-loss is placed immediately after the entry is confirmed.

-   **Target:**
    -   The `HunterTrade` **does not have a predefined profit target**.
    -   Its exit is primarily managed by the dynamic stop-loss. The trade is designed to capture the initial, sharp reversal. The position will be closed either by the trailing stop-loss or by the global stop-loss monitoring function if the price moves against the position.

---

### **Trade Type: P2P (Point-to-Point) Trend Trade**

-   **Conditions:**
    -   The "Day Type" must be classified as either a **Bullish Trend** (`Opening Price > Hunter Zone High` AND `PCR > 1.2`) or a **Bearish Trend** (`Opening Price < Hunter Zone Low` AND `PCR < 0.7`).
    -   The absolute **Microstructure Confluence Score** must be `>= 7`.
    -   No open position for the instrument should already exist.

-   **Reasons:**
    -   This trade is designed to participate in **strong, confirmed trend days**.
    -   The combination of a price gap in one direction and a contrarian, overcrowded sentiment in the other (high PCR for a bull trend, low PCR for a bear trend) creates the conditions for a powerful, sustained move as positions are unwound.
    -   The edge comes from identifying a high-probability trend at the start of the day and riding the momentum. The Microstructure Score ensures the bot enters only when the underlying momentum is strong and established.

-   **Setup:**
    -   The market opens with a significant gap and the PCR confirms a high likelihood of a trend day.
    -   The bot is looking for the first strong momentum signal in the direction of the established trend.

-   **Entry:**
    -   The trigger is a **Microstructure Confluence Score of +/- 7 or greater** in the direction of the trend.
    -   For a Bullish Trend day, the bot waits for a score of `>= 7` and buys an **ATM Call Option**.
    -   For a Bearish Trend day, the bot waits for a score of `<= -7` and buys an **ATM Put Option**.

-   **SL (Stop-Loss):**
    -   The Stop-Loss is **dynamic**, similar to the Hunter Trade, but with more room to accommodate trend pullbacks.
    -   It is calculated based on the last swing point buffered by `1.5 * ATR`. This wider stop is designed to prevent the trade from being stopped out by normal volatility within a strong trend.

-   **Target:**
    -   The target is **dynamic and based on momentum, not a fixed price**.
    -   The primary exit condition is a **reversal of the Microstructure Score**.
    -   If in a long (bullish) position, the trade is closed when the score flips to become negative.
    -   If in a short (bearish) position, the trade is closed when the score flips to become positive.
    -   This allows the bot to ride the trend for as long as the momentum persists and exit as soon as it shows signs of reversal.

---

### **Trade Type: Mean Reversion**

-   **Conditions:**
    -   The "Day Type" must be classified as **Sideways/Choppy** (opening price is within the Hunter Zone).
    -   No open position for the instrument should already exist.
    -   The current price must have deviated by at least **1%** from the 5-minute Elastic Volume Weighted Moving Average (EVWMA).

-   **Reasons:**
    -   This trade operates on the principle that on a choppy or range-bound day, prices tend to revert to their short-term average.
    -   When the market lacks a clear directional bias, extreme moves away from the "mean" (the 5m EVWMA) are often unsustainable and present short-term fading opportunities.
    -   The edge comes from taking a contrarian position at a point of statistical extremity, with the expectation that the price will snap back to its average.

-   **Setup:**
    -   The market is identified as being in a sideways or choppy state.
    -   The bot monitors the price relative to the 5-minute EVWMA, waiting for it to stretch significantly.

-   **Entry:**
    -   Entry is **not based on the Microstructure Score**.
    -   The trigger is purely based on deviation from the mean.
    -   If `price > evwma_5m * 1.01` (1% above the mean), the bot initiates a **short** trade by buying an **ATM Put Option**.
    -   If `price < evwma_5m * 0.99` (1% below the mean), the bot initiates a **long** trade by buying an **ATM Call Option**.

-   **SL (Stop-Loss):**
    -   The Stop-Loss is **dynamic and tighter** than other strategies.
    -   It uses the last swing point buffered by `0.7 * ATR`. This reflects the strategy's goal of capturing a quick scalp-like move; if the price continues to move away from the mean, the trade is cut quickly.

-   **Target:**
    -   The target is **the mean itself**.
    -   The exit condition is triggered when the price reverts and **touches the 1-minute EVWMA**.
    -   This is a quick scalp trade, designed to capture the profit from the snap-back to the short-term average.
