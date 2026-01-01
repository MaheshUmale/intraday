# Configuration for the trading bot

# PCR (Put-Call Ratio) thresholds for Day Type Classification
PCR_BULLISH = 1.2
PCR_BEARISH = 0.7
PCR_BULL_TRAP = 0.9
PCR_BEAR_TRAP = 1.1

# Microstructure Confluence Score threshold
SCORE_THRESHOLD = 7

# ATR (Average True Range) multipliers for Stop-Loss calculation
ATR_MULTIPLIER_SCALP = 0.7
ATR_MULTIPLIER_HUNTER = 1.2
ATR_MULTIPLIER_P2P_TREND = 1.5

# Probability Score threshold for trade execution
PROBABILITY_THRESHOLD = 75

# Relative Volume (RVOL) spike threshold for exit signal
RVOL_SPIKE_THRESHOLD = 4

# Instruments to trade
INSTRUMENTS = [
    "NSE_INDEX|Nifty 50",
    "NSE_INDEX|Nifty Bank"
]

# Exchange to trade on
EXCHANGE = "NSE"

# Paper trading mode
PAPER_TRADING = True

# Advanced Volume Analysis
USE_ADVANCED_VOLUME_ANALYSIS = True
