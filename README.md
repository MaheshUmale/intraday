This summary serves as the **Master Logic Document** for the algorithmic trading system we have architected. It codifies every structural rule, tactical nuance, and risk management principle discussed, moving away from code to focus entirely on the **Intelligence Framework**.

---

### **Part 1: The Macro Framework – Day Type Classification**

The foundational principle of our system is that **Context dictates Tactics**. A strategy that works in a trending market will fail in a sideways market. Therefore, the first task of the engine at 09:15 AM is to classify the "Regime" or **Day Type**.

#### **1.1 The Reference Zone (The Hunter Zone)**

Before the market opens, the engine identifies the **Hunter Zone**, defined as the price range (High and Low) of the **final 60 minutes of the previous trading day**. This zone represents the most recent institutional "fair value" before the close.

#### **1.2 The Five Day Type Regimes**

The Day Type is determined by the relationship between the **Opening Price**, the **Hunter Zone**, and the **Configurable PCR (Put-Call Ratio)** thresholds.

* **Type 1: Bullish Trend Day**
* **Logic**: Market opens above the Prev Day High (Gap Up) and the PCR is high (e.g., > 1.2).
* **Character**: Suggests aggressive institutional buying and "Acceptance" of higher prices.


* **Type 2: Bearish Trend Day**
* **Logic**: Market opens below the Prev Day Low (Gap Down) and the PCR is low (e.g., < 0.7).
* **Character**: Suggests aggressive institutional selling and "Acceptance" of lower prices.


* **Type 3: Sideways Bull Trap (Hunter Short Context)**
* **Logic**: Market gaps up above the Prev Day High, but the PCR is bearish or neutral (e.g., < 0.9).
* **Character**: The "Gap" is unsupported by options sentiment, making it a prime candidate for a "Hunter Rejection."


* **Type 4: Sideways Bear Trap (Hunter Long Context)**
* **Logic**: Market gaps down below the Prev Day Low, but the PCR is bullish (e.g., > 1.1).
* **Character**: The downward move lacks sentiment conviction, leading to a high probability of a "Mean Reversion" spike.


* **Type 5: Sideways/Choppy Day**
* **Logic**: Market opens inside the previous day's range with neutral PCR.
* **Character**: Most trades will be "Responsive" (buying lows, selling highs) rather than "Initiative" (trending).



---

### **Part 2: The Tactical Templates (Execution Archetypes)**

Once the Day Type is set, the engine "unlocks" specific tactical templates. A professional system never applies the same exit or SL logic to a scalp as it does to a trend trade.

#### **2.1 The Hunter Trade (The Core Alpha)**

The Hunter trade focuses on the first 45 minutes of trade (09:15 – 10:00). It is designed to profit from the "Morning Trap."

**The 6 Hunter Combinations (Acceptance vs. Rejection):**

1. **Gap Up Rejection**: Price opens above the zone, spikes higher to induce "FOMO," then the Microstructure Score flips bearish. **Action**: Short back to the EVWMA.
2. **Gap Up Acceptance**: Price opens above the zone, tests the High, but the Score remains strongly bullish. **Action**: Long for a Trend Day.
3. **Gap Down Rejection**: Price opens below the zone, induces panic selling, then the Score flips bullish at a structural pivot. **Action**: Long.
4. **Gap Down Acceptance**: Price holds below the Low with increasing bearish volume force. **Action**: Short.
5. **Inside Initiative**: Price opens inside the zone but breaks a boundary with a high Confluence Score.
6. **Inside Responsive**: Price tests a boundary, fails to break, and returns to the center.

#### **2.2 Point-to-Point (P2P) Trend**

This template is for high-conviction moves. It ignores minor mean-reversions and stays in the trade as long as the **Total Score** remains above the threshold (e.g., +7). It targets "OI Walls" (Option strikes with maximum Open Interest).

#### **2.3 The Scalp (Micro-Momentum)**

Scalps are fast, 1-3 candle moves triggered by **Delta-Price Divergence** (where price moves one way but volume force suggests the other). These have the tightest risk parameters.

#### **2.4 Mean Reversion**

Active only on Sideways days. The price is treated like a rubber band; as it stretches away from the **EVWMA (Elastic Volume Weighted MA)**, the engine looks for exhaustion to trade back to the "Value Area."

---

### **Part 3: The Engine – Microstructure Scoring (+/- 12)**

The "brain" of the system is the **Microstructure Confluence Score**. It avoids the lag of traditional indicators by using volume-force logic.

#### **3.1 Multi-Timeframe Alignment**

A trade is only taken when the **1-minute** and **5-minute** timeframes are in "Sync."

* **dyn5 (5 pts)**: Direction of price vs. 5m EVWMA.
* **dyn1 (1 pt)**: Direction of price vs. 1m EVWMA.
* **evm5 (5 pts)**: Slope/Momentum of the 5m EVWMA.
* **evm1 (1 pt)**: Slope/Momentum of the 1m EVWMA.

**Total Max Score: +12 (Ultra Bullish) to -12 (Ultra Bearish).**
A score of **+/- 7** is the minimum threshold for high-conviction entries.

---

### **Part 4: Pre-emptive Risk Planning (The "Professional" Layer)**

This is where most systems fail. Professional planning happens *before* the order is sent.

#### **4.1 Dynamic Stop-Loss (ATR + Structure)**

We rejected fixed-point Stop Losses (e.g., "30 points") because they are arbitrary. Instead:

* **The Volatility Buffer**: SL is calculated as a multiple of the **ATR (Average True Range)**.
* **The Structural Buffer**: The engine looks at the last 10-20 candles to find the "Recent Swing." The SL is placed slightly beyond that swing (the "Non-Obvious" level) to avoid being hunted by "wick" spikes.

#### **4.2 Trade-Specific SL Multipliers**

* **Scalp**: 0.7x ATR (Very tight, "be right or get out").
* **Hunter**: 1.2x ATR (Needs room for morning volatility).
* **P2P Trend**: 1.5x ATR (Gives the trend room to breathe).

#### **4.3 Probability Weighting**

Every trade is assigned a **Probability Score (0-100%)**:

* **PCR Alignment**: +20% if PCR supports the direction.
* **Index Sync**: +30% if NIFTY and BANKNIFTY are moving in unison.
* **Score Force**: +30% if Score is > 10.
* **Value Area**: +20% if entry is near the VWAP/EVWMA.
Only trades with **> 75% Probability** are executed with full position size.

---

### **Part 5: The Reason to Exit (Institutional Exhaustion)**

The system does not wait for an arbitrary target if the market conditions change. The primary exit signal is the **4x RVOL (Relative Volume) Spike**.

When volume suddenly spikes to 4 times the 20-period average, it signifies **Institutional Climax** (either profit-taking or a massive counter-move). The engine treats this as an immediate exit signal to protect unrealized gains.

---

### **Conclusion: The Logic Loop**

1. **09:00**: Map instruments (ATM/OTM strikes) using `ExtractInstrumentKeys.py`.
2. **09:15**: Observe Open vs. Hunter Zone + PCR; Set **Day Type**.
3. **09:16 - 10:00**: Monitor for **Hunter Combinations** at boundaries.
4. **All Day**: Calculate **Total Score (+/- 12)**. If sync occurs, calculate **Probability**.
5. **Execution**: Plan SL/TP pre-emptively based on ATR; Send **GTT Order** (Entry + SL + TP) as a single packet.
6. **Monitoring**: Exit on **4x RVOL Spike** or **Score Flip**.
