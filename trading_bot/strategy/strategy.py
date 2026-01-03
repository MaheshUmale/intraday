from enum import Enum
import trading_bot.config as config
import logging
import pandas as pd
import pandas_ta as ta

# Create a dedicated logger for trades from the main module
trade_logger = logging.getLogger('trade_logger')

class DayType(Enum):
    """
    Enum representing the classification of the market day type.
    This classification determines which trading strategy (Tactical Template) to use.
    """
    BULLISH_TREND = "Bullish Trend"
    BEARISH_TREND = "Bearish Trend"
    SIDEWAYS_BULL_TRAP = "Sideways Bull Trap"
    SIDEWAYS_BEAR_TRAP = "Sideways Bear Trap"
    SIDEWAYS_CHOPPY = "Sideways/Choppy"

def classify_day_type(opening_price, hunter_zone_high, hunter_zone_low, pcr):
    """
    Classifies the day type based on the opening price relative to the Hunter Zone
    and the Put-Call Ratio (PCR).

    Args:
        opening_price (float): The opening price of the instrument for the day.
        hunter_zone_high (float): The high of the Hunter Zone.
        hunter_zone_low (float): The low of the Hunter Zone.
        pcr (float): The current Put-Call Ratio.

    Returns:
        DayType: The classified day type.
    """
    if opening_price > hunter_zone_high and pcr > 1.2:
        return DayType.BULLISH_TREND
    elif opening_price < hunter_zone_low and pcr < 0.7:
        return DayType.BEARISH_TREND
    elif opening_price > hunter_zone_high and pcr < 0.9:
        return DayType.SIDEWAYS_BULL_TRAP
    elif opening_price < hunter_zone_low and pcr > 1.1:
        return DayType.SIDEWAYS_BEAR_TRAP
    else:
        return DayType.SIDEWAYS_CHOPPY

class TacticalTemplate:
    """
    Base class for all trading strategies (Tactical Templates).
    Defines the common interface for strategy execution.
    """
    def __init__(self, order_manager):
        self.order_manager = order_manager

    def execute(self, **kwargs):
        """
        The main execution method for a strategy. This must be implemented by subclasses.
        """
        raise NotImplementedError

def find_atm_strike(price):
    """
    Finds the at-the-money (ATM) strike price by rounding to the nearest 50.
    """
    return int(round(price / 50) * 50)

def get_atm_option_instrument(option_chain, atm_strike, direction):
    """
    Finds the instrument key for the ATM call or put option.

    Args:
        option_chain (list): The list of option chain data from the API.
        atm_strike (int): The calculated at-the-money strike price.
        direction (str): The trade direction, 'BULL' for call, 'BEAR' for put.

    Returns:
        str: The instrument key of the ATM option, or None if not found.
    """
    if not option_chain:
        return None

    for strike_data in option_chain:
        if strike_data.strike_price == atm_strike:
            if direction == 'BULL' and strike_data.call_options:
                return strike_data.call_options.instrument_key
            elif direction == 'BEAR' and strike_data.put_options:
                return strike_data.put_options.instrument_key
    return None

class HunterTrade(TacticalTemplate):
    """
    Implements the "Hunter" tactical template.
    This strategy is typically used in sideways markets to trade breakouts
    from the Hunter Zone, qualified by microstructure and probability scores.
    Exit logic is handled externally by the main bot's stop-loss monitoring.
    """
    def execute(self, **kwargs):
        """
        Executes the Hunter Trade logic.

        Args:
            **kwargs: A dictionary of strategy parameters including score, price,
                      instrument_key, option_chain, open_positions, df, pcr, etc.
        """
        score = kwargs.get('score')
        price = kwargs.get('price')
        instrument_key = kwargs.get('instrument_key')
        option_chain = kwargs.get('option_chain')
        open_positions = kwargs.get('open_positions')
        df = kwargs.get('df')
        pcr = kwargs.get('pcr')

        if abs(score) >= config.SCORE_THRESHOLD:
            # Calculate probability score
            pcr_alignment = (pcr > 1.0 and score > 0) or (pcr < 1.0 and score < 0)
            index_sync = True  # Placeholder
            value_area = price > kwargs.get('hunter_zone')['low'] and price < kwargs.get('hunter_zone')['high']
            probability_score = calculate_probability_score(
                pcr_alignment=pcr_alignment,
                index_sync=index_sync,
                score_force=abs(score) > 10,
                value_area=value_area
            )

            if probability_score < config.PROBABILITY_THRESHOLD:
                logging.info(f"Probability score {probability_score} is below threshold. Skipping trade.")
                return

            direction = 'BULL' if score > 0 else 'BEAR'
            transaction_type = "BUY"

            # Find the ATM strike and the corresponding option instrument.
            atm_strike = find_atm_strike(price)
            option_instrument_key = get_atm_option_instrument(option_chain, atm_strike, direction)

            if not option_instrument_key:
                logging.warning(f"Could not find ATM option for {instrument_key} at strike {atm_strike}. Skipping trade.")
                return

            # Place a market order
            vpa_signal = kwargs.get('vpa_signal')
            timestamp = kwargs.get('timestamp')
            logging.info(f"Placing Hunter trade for {instrument_key}. Score: {score}, Probability: {probability_score}, VPA: {vpa_signal}")
            trade_logger.info(f"ENTRY: Hunter, {instrument_key}, {direction}, {price}, {score}, {probability_score}, {vpa_signal}")
            order_response = self.order_manager.place_order(
                quantity=1,
                product="I",
                validity="DAY",
                price=0,
                instrument_token=option_instrument_key,
                order_type="MARKET",
                transaction_type=transaction_type,
                tag="hunter_trade",
                timestamp=timestamp
            )

            if order_response:
                df = calculate_atr(df)
                atr = df['atr'].iloc[-1]
                last_swing = find_recent_swing(df, direction)
                stop_loss_price = calculate_stop_loss(atr, "Hunter", last_swing, direction, price)

                self.order_manager.place_gtt_order(
                    instrument_token=option_instrument_key,
                    transaction_type="SELL",
                    trigger_price=stop_loss_price,
                    price=stop_loss_price,
                    quantity=1
                )

                # Add to open positions
                open_positions[instrument_key] = {
                    'order_id': order_response.order_id,
                    'instrument_key': option_instrument_key,
                    'transaction_type': transaction_type,
                    'entry_price': price,
                    'stop_loss_price': stop_loss_price,
                    'direction': direction
                }

class P2PTrend(TacticalTemplate):
    """
    Implements the Point-to-Point (P2P) Trend tactical template.
    This strategy is used in trending markets. It enters a position based on a
    strong microstructure score and holds it until the score flips, indicating
    a potential reversal.
    """
    def execute(self, **kwargs):
        """
        Executes the P2P Trend logic.

        If a position is open, it checks if the score has flipped to exit.
        If no position is open, it checks for a strong score to enter a new position.

        Args:
            **kwargs: A dictionary of strategy parameters.
        """
        score = kwargs.get('score')
        price = kwargs.get('price')
        instrument_key = kwargs.get('instrument_key')
        open_positions = kwargs.get('open_positions')

        if instrument_key in open_positions:
            position = open_positions[instrument_key]
            # Hold the position until the score flips
            if (score > 0 and position['direction'] == "BEAR") or \
               (score < 0 and position['direction'] == "BULL"):
                logging.info(f"Score flipped for {instrument_key}. Closing position.")
                trade_logger.info(f"EXIT: P2P Trend, {instrument_key}, {position['direction']}, {price}, {score}")
                timestamp = kwargs.get('timestamp')
                self.order_manager.place_order(
                    quantity=1,
                    product="I",
                    validity="DAY",
                    price=0,
                    instrument_token=position['instrument_key'],
                    order_type="MARKET",
                    transaction_type="SELL",
                    tag="p2p_trend_exit",
                    timestamp=timestamp
                )
                self.order_manager.close_paper_position(
                    instrument_key=position['instrument_key'],
                    exit_price=price,
                    exit_time=timestamp
                )
                if instrument_key in open_positions:
                    del open_positions[instrument_key]
        elif abs(score) >= config.SCORE_THRESHOLD:
            # Enter a new position
            direction = 'BULL' if score > 0 else 'BEAR'
            transaction_type = "BUY"

            # Find the ATM strike and the corresponding option instrument.
            atm_strike = find_atm_strike(price)
            option_instrument_key = get_atm_option_instrument(kwargs.get('option_chain'), atm_strike, direction)

            if not option_instrument_key:
                logging.warning(f"Could not find ATM option for {instrument_key} at strike {atm_strike}. Skipping trade.")
                return

            vpa_signal = kwargs.get('vpa_signal')
            timestamp = kwargs.get('timestamp')
            logging.info(f"Placing P2P Trend trade for {instrument_key}. Score: {score}, VPA: {vpa_signal}")
            trade_logger.info(f"ENTRY: P2P Trend, {instrument_key}, {direction}, {price}, {score}, {vpa_signal}")
            order_response = self.order_manager.place_order(
                quantity=1,
                product="I",
                validity="DAY",
                price=0,
                instrument_token=option_instrument_key,
                order_type="MARKET",
                transaction_type=transaction_type,
                tag="p2p_trend",
                timestamp=timestamp
            )

            if order_response:
                df = calculate_atr(kwargs.get('df'))
                atr = df['atr'].iloc[-1]
                last_swing = find_recent_swing(df, direction)
                stop_loss_price = calculate_stop_loss(atr, "P2P Trend", last_swing, direction, price)

                self.order_manager.place_gtt_order(
                    instrument_token=option_instrument_key,
                    transaction_type="SELL",
                    trigger_price=stop_loss_price,
                    price=stop_loss_price,
                    quantity=1
                )

                open_positions[instrument_key] = {
                    'order_id': order_response.order_id,
                    'instrument_key': option_instrument_key,
                    'transaction_type': transaction_type,
                    'entry_price': price,
                    'stop_loss_price': stop_loss_price,
                    'direction': direction
                }

class Scalp(TacticalTemplate):
    """
    Placeholder for the Scalp tactical template.
    This strategy is not yet implemented.
    """
    def execute(self, **kwargs):
        """
        Executes the Scalp trading strategy.
        Placeholder implementation.
        """
        logging.info("Scalp strategy is not yet implemented.")

class MeanReversion(TacticalTemplate):
    """
    Implements the Mean Reversion tactical template.
    This strategy is used in choppy/sideways markets. It enters a trade when
    the price deviates significantly from its short-term mean (EVWMA) and
    exits when it reverts back to the mean.
    """
    def execute(self, **kwargs):
        """
        Executes the Mean Reversion logic.

        If a position is open, it checks for price reversion to exit.
        If no position is open, it checks for significant price deviation to enter.

        Args:
            **kwargs: A dictionary of strategy parameters.
        """
        price = kwargs.get('price')
        instrument_key = kwargs.get('instrument_key')
        evwma_1m = kwargs.get('evwma_1m')
        evwma_5m = kwargs.get('evwma_5m')
        open_positions = kwargs.get('open_positions')

        if pd.isna(evwma_1m) or pd.isna(evwma_5m):
            logging.warning(f"EVWMA values are not available for {instrument_key}. Skipping MeanReversion strategy.")
            return

        if instrument_key in open_positions:
            position = open_positions[instrument_key]
            # Close the position if the price has reverted to the mean
            if (position['direction'] == "BULL" and price >= evwma_1m) or \
               (position['direction'] == "BEAR" and price <= evwma_1m):
                logging.info(f"Price reverted for {instrument_key}. Closing position.")
                trade_logger.info(f"EXIT: Mean Reversion, {instrument_key}, {position['direction']}, {price}")
                timestamp = kwargs.get('timestamp')
                self.order_manager.place_order(
                    quantity=1,
                    product="I",
                    validity="DAY",
                    price=0,
                    instrument_token=position['instrument_key'],
                    order_type="MARKET",
                    transaction_type="SELL",
                    tag="mean_reversion_exit",
                    timestamp=timestamp
                )
                self.order_manager.close_paper_position(
                    instrument_key=position['instrument_key'],
                    exit_price=price,
                    exit_time=timestamp
                )
                if instrument_key in open_positions:
                    del open_positions[instrument_key]
        else:
            # Enter a new position if the price has stretched away from the EVWMA
            direction = None
            if price > evwma_5m * 1.01: # 1% above EVWMA
                direction = 'BEAR'
            elif price < evwma_5m * 0.99: # 1% below EVWMA
                direction = 'BULL'

            if direction:
                transaction_type = "BUY"

                # Find the ATM strike and the corresponding option instrument.
                atm_strike = find_atm_strike(price)
                option_instrument_key = get_atm_option_instrument(kwargs.get('option_chain'), atm_strike, direction)

                if not option_instrument_key:
                    logging.warning(f"Could not find ATM option for {instrument_key} at strike {atm_strike}. Skipping trade.")
                    return

                vpa_signal = kwargs.get('vpa_signal')
                timestamp = kwargs.get('timestamp')
                logging.info(f"Placing Mean Reversion trade for {instrument_key}. Price: {price}, EVWMA_5m: {evwma_5m}, VPA: {vpa_signal}")
                trade_logger.info(f"ENTRY: Mean Reversion, {instrument_key}, {direction}, {price}, EVWMA_5m: {evwma_5m}, {vpa_signal}")
                order_response = self.order_manager.place_order(
                    quantity=1,
                    product="I",
                    validity="DAY",
                    price=0,
                    instrument_token=option_instrument_key,
                    order_type="MARKET",
                    transaction_type=transaction_type,
                    tag="mean_reversion",
                    timestamp=timestamp
                )

                if order_response:
                    df = calculate_atr(kwargs.get('df'))
                    atr = df['atr'].iloc[-1]
                    last_swing = find_recent_swing(df, direction)
                    stop_loss_price = calculate_stop_loss(atr, "Scalp", last_swing, direction, price) # Using Scalp ATR multiplier

                    self.order_manager.place_gtt_order(
                        instrument_token=option_instrument_key,
                        transaction_type="SELL",
                        trigger_price=stop_loss_price,
                        price=stop_loss_price,
                        quantity=1
                    )

                    open_positions[instrument_key] = {
                        'order_id': order_response.order_id,
                        'instrument_key': option_instrument_key,
                        'transaction_type': transaction_type,
                        'entry_price': price,
                        'stop_loss_price': stop_loss_price,
                        'direction': direction
                    }

def calculate_pcr(option_chain):
    """
    Calculates the Put-Call Ratio (PCR) from the option chain data.
    """
    total_put_oi = 0
    total_call_oi = 0
    if not option_chain:
        return 1.0  # Neutral PCR if data is unavailable

    for strike_data in option_chain:
        if strike_data.put_options and strike_data.put_options.market_data:
            total_put_oi += strike_data.put_options.market_data.oi or 0
        if strike_data.call_options and strike_data.call_options.market_data:
            total_call_oi += strike_data.call_options.market_data.oi or 0

    if total_call_oi == 0:
        return 100.0  # Assign a high value if no calls, indicating extreme bullishness

    return total_put_oi / total_call_oi

def calculate_evwma(df, length=20):
    """
    Calculates the Elastic Volume Weighted Moving Average (EVWMA) and its slope.
    """
    # Ensure columns exist to prevent KeyErrors
    if df.empty or 'volume' not in df.columns or 'close' not in df.columns:
        df['evwma'] = pd.NA
        df['evwma_slope'] = pd.NA
        return df

    # Clean data: ensure numeric types and handle missing values
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
    df['close'] = pd.to_numeric(df['close'], errors='coerce').ffill()

    # If not enough data points for the indicator, return with null columns
    if len(df.dropna(subset=['close', 'volume'])) < length:
        df['evwma'] = pd.NA
        df['evwma_slope'] = pd.NA
        return df

    # Calculate indicators
    df['evwma'] = ta.vwma(close=df['close'], volume=df['volume'], length=length)
    df['evwma_slope'] = df['evwma'].diff()
    return df

def calculate_microstructure_score(price, evwma_1m, evwma_5m, evwma_1m_slope, evwma_5m_slope):
    """
    Calculates the Microstructure Confluence Score.
    """
    score = 0
    if pd.isna(evwma_1m) or pd.isna(evwma_5m) or pd.isna(evwma_1m_slope) or pd.isna(evwma_5m_slope):
        return score

    # dyn5: Direction of price vs. 5m EVWMA
    if price > evwma_5m: score += 5
    elif price < evwma_5m: score -= 5

    # dyn1: Direction of price vs. 1m EVWMA
    if price > evwma_1m: score += 1
    elif price < evwma_1m: score -= 1

    # evm5: Slope/Momentum of the 5m EVWMA
    if evwma_5m_slope > 0: score += 5
    elif evwma_5m_slope < 0: score -= 5

    # evm1: Slope/Momentum of the 1m EVWMA
    if evwma_1m_slope > 0: score += 1
    elif evwma_1m_slope < 0: score -= 1

    return score

def calculate_stop_loss(atr, trade_type, last_swing, direction, entry_price):
    """
    Calculates the stop-loss based on ATR, trade type, and the last swing.
    """
    multipliers = {"Scalp": 0.7, "Hunter": 1.2, "P2P Trend": 1.5}
    multiplier = multipliers.get(trade_type, 1.0)
    volatility_buffer = multiplier * atr if pd.notna(atr) else entry_price * 0.01 # Fallback to 1%

    if direction == "BULL":
        return last_swing - volatility_buffer
    else: # BEAR
        return last_swing + volatility_buffer

def calculate_probability_score(pcr_alignment, index_sync, score_force, value_area):
    """
    Calculates the probability score for a trade.
    """
    score = 0
    if pcr_alignment: score += 20
    if index_sync: score += 30
    if score_force: score += 30
    if value_area: score += 20
    return score

def calculate_atr(df, length=14):
    """
    Calculates the Average True Range (ATR).
    """
    if df.empty: return df
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=length)
    return df

def find_recent_swing(df, direction, n=20):
    """
    Finds the most recent swing high or low from the last n candles.
    """
    if df.empty: return 0
    df_slice = df.iloc[-n:]
    if direction == 'BULL':
        return df_slice['low'].min()
    else: # BEAR
        return df_slice['high'].max()

def detect_pocket_pivot_volume(df, lookback=10):
    """
    Detects Pocket Pivot Volume (PPV).
    """
    if len(df) < lookback + 1: return False
    latest_bar = df.iloc[-1]
    if latest_bar['close'] <= latest_bar['open']: return False

    lookback_df = df.iloc[-lookback-1:-1]
    down_volume = lookback_df[lookback_df['close'] < lookback_df['open']]['volume']

    return not down_volume.empty and latest_bar['volume'] > down_volume.max()

def detect_pivot_negative_volume(df, lookback=10):
    """
    Detects Pivot Negative Volume (PNV).
    """
    if len(df) < lookback + 1: return False
    latest_bar = df.iloc[-1]
    if latest_bar['close'] >= latest_bar['open']: return False

    lookback_df = df.iloc[-lookback-1:-1]
    up_volume = lookback_df[lookback_df['close'] > lookback_df['open']]['volume']

    return not up_volume.empty and latest_bar['volume'] > up_volume.max()

def detect_accumulation(df):
    """
    Detects accumulation.
    """
    if len(df) < 2: return False
    latest_bar = df.iloc[-1]
    range_val = latest_bar['high'] - latest_bar['low']
    avg_range = (df['high'].iloc[:-1] - df['low'].iloc[:-1]).mean()
    avg_volume = df['volume'].iloc[:-1].mean()

    return latest_bar['volume'] > avg_volume * 1.5 and range_val < avg_range * 0.7 and latest_bar['close'] > latest_bar['open']

def detect_distribution(df):
    """
    Detects distribution.
    """
    if len(df) < 2: return False
    latest_bar = df.iloc[-1]
    range_val = latest_bar['high'] - latest_bar['low']
    avg_range = (df['high'].iloc[:-1] - df['low'].iloc[:-1]).mean()
    avg_volume = df['volume'].iloc[:-1].mean()

    return latest_bar['volume'] > avg_volume * 1.5 and range_val < avg_range * 0.7 and latest_bar['close'] < latest_bar['open']
