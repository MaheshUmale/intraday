from enum import Enum
import trading_bot.config as config
import logging
import pandas as pd
import pandas_ta as ta

class DayType(Enum):
    BULLISH_TREND = "Bullish Trend"
    BEARISH_TREND = "Bearish Trend"
    SIDEWAYS_BULL_TRAP = "Sideways Bull Trap"
    SIDEWAYS_BEAR_TRAP = "Sideways Bear Trap"
    SIDEWAYS_CHOPPY = "Sideways/Choppy"

def classify_day_type(opening_price, hunter_zone_high, hunter_zone_low, pcr):
    """
    Classifies the day type based on the opening price, hunter zone, and PCR.
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
    def __init__(self, order_manager):
        self.order_manager = order_manager

    def execute(self, **kwargs):
        raise NotImplementedError

def find_atm_strike(price):
    """
    Finds the at-the-money (ATM) strike price.
    """
    return int(round(price / 100) * 100)

class HunterTrade(TacticalTemplate):
    # Note: HunterTrade does not have its own exit logic.
    # Exits are handled by the main application's stop-loss monitoring.
    def execute(self, **kwargs):
        """
        Executes the Hunter Trade strategy.
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

            transaction_type = "BUY"

            # Find the ATM strike and the corresponding instrument key
            atm_strike = find_atm_strike(price)
            option_instrument_key = None

            for item in option_chain:
                if hasattr(item, 'strike_price') and item.strike_price == atm_strike:
                    if score > 0 and hasattr(item, 'call_options'):
                        option_instrument_key = item.call_options.instrument_key
                        break
                    elif score < 0 and hasattr(item, 'put_options'):
                        option_instrument_key = item.put_options.instrument_key
                        break

            if not option_instrument_key:
                logging.warning(f"Could not find ATM option for {instrument_key}. Skipping trade.")
                return

            # Place a market order
            vpa_signal = kwargs.get('vpa_signal')
            logging.info(f"Placing Hunter trade for {instrument_key}. Score: {score}, Probability: {probability_score}, VPA: {vpa_signal}")
            trade_logger.info(f"ENTRY: Hunter, {instrument_key}, {transaction_type}, {price}, {score}, {probability_score}, {vpa_signal}")
            order_response = self.order_manager.place_order(
                quantity=1,
                product="I",
                validity="DAY",
                price=0,
                instrument_token=option_instrument_key,
                order_type="MARKET",
                transaction_type=transaction_type,
                tag="hunter_trade"
            )

            if order_response:
                # Calculate and place stop-loss order
                df = calculate_atr(df)
                atr = df['atr'].iloc[-1]
                direction = 'BULL' if score > 0 else 'BEAR'
                last_swing = find_recent_swing(df, direction)
                stop_loss_price = calculate_stop_loss(atr, "Hunter", last_swing, direction)

                self.order_manager.place_gtt_order(
                    instrument_token=option_instrument_key,
                    transaction_type="SELL" if transaction_type == "BUY" else "BUY",
                    trigger_price=stop_loss_price,
                    price=stop_loss_price - 1, # Limit price for stop-loss
                    quantity=1
                )

                # Add to open positions
                open_positions[instrument_key] = {
                    'order_id': order_response.order_id,
                    'instrument_key': option_instrument_key,
                    'transaction_type': transaction_type,
                    'entry_price': price,
                    'stop_loss_price': stop_loss_price,
                    'direction': 'BULL' if score > 0 else 'BEAR'
                }

class P2PTrend(TacticalTemplate):
    def execute(self, **kwargs):
        """
        Executes the Point-to-Point Trend strategy.
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
                trade_logger.info(f"EXIT: P2P Trend, {instrument_key}, {position['transaction_type']}, {price}, {score}")
                self.order_manager.place_order(
                    quantity=1,
                    product="I",
                    validity="DAY",
                    price=0,
                    instrument_token=position['instrument_key'],
                    order_type="MARKET",
                    transaction_type="SELL",
                    tag="p2p_trend_exit"
                )
                self.order_manager.close_paper_position(position['instrument_key'])
                del open_positions[instrument_key]
        elif abs(score) >= config.SCORE_THRESHOLD:
            # Enter a new position
            transaction_type = "BUY"

            # Find the ATM strike and the corresponding instrument key
            atm_strike = find_atm_strike(price)
            option_instrument_key = None

            for item in kwargs.get('option_chain'):
                if hasattr(item, 'strike_price') and item.strike_price == atm_strike:
                    if score > 0 and hasattr(item, 'call_options'):
                        option_instrument_key = item.call_options.instrument_key
                        break
                    elif score < 0 and hasattr(item, 'put_options'):
                        option_instrument_key = item.put_options.instrument_key
                        break

            if not option_instrument_key:
                logging.warning(f"Could not find ATM option for {instrument_key}. Skipping trade.")
                return

            vpa_signal = kwargs.get('vpa_signal')
            logging.info(f"Placing P2P Trend trade for {instrument_key}. Score: {score}, VPA: {vpa_signal}")
            trade_logger.info(f"ENTRY: P2P Trend, {instrument_key}, {transaction_type}, {price}, {score}, {vpa_signal}")
            order_response = self.order_manager.place_order(
                quantity=1,
                product="I",
                validity="DAY",
                price=0,
                instrument_token=option_instrument_key,
                order_type="MARKET",
                transaction_type=transaction_type,
                tag="p2p_trend"
            )

            if order_response:
                df = calculate_atr(kwargs.get('df'))
                atr = df['atr'].iloc[-1]
                direction = 'BULL' if score > 0 else 'BEAR'
                last_swing = find_recent_swing(df, direction)
                stop_loss_price = calculate_stop_loss(atr, "P2P Trend", last_swing, direction)

                self.order_manager.place_gtt_order(
                    instrument_token=option_instrument_key,
                    transaction_type="SELL" if transaction_type == "BUY" else "BUY",
                    trigger_price=stop_loss_price,
                    price=stop_loss_price - 1,
                    quantity=1
                )

                open_positions[instrument_key] = {
                    'order_id': order_response.order_id,
                    'instrument_key': option_instrument_key,
                    'transaction_type': transaction_type,
                    'entry_price': price,
                    'stop_loss_price': stop_loss_price,
                    'direction': 'BULL' if score > 0 else 'BEAR'
                }

class Scalp(TacticalTemplate):
    def execute(self, **kwargs):
        """
        Executes the Scalp trading strategy.
        Placeholder implementation.
        """
        logging.info("Scalp strategy is not yet implemented.")

class MeanReversion(TacticalTemplate):
    def execute(self, **kwargs):
        """
        Executes the Mean Reversion strategy.
        """
        price = kwargs.get('price')
        instrument_key = kwargs.get('instrument_key')
        evwma_1m = kwargs.get('evwma_1m')
        evwma_5m = kwargs.get('evwma_5m')
        open_positions = kwargs.get('open_positions')

        if instrument_key in open_positions:
            position = open_positions[instrument_key]
            # Close the position if the price has reverted to the mean
            if (position['direction'] == "BULL" and price >= evwma_1m) or \
               (position['direction'] == "BEAR" and price <= evwma_1m):
                logging.info(f"Price reverted for {instrument_key}. Closing position.")
                trade_logger.info(f"EXIT: Mean Reversion, {instrument_key}, {position['transaction_type']}, {price}")
                self.order_manager.place_order(
                    quantity=1,
                    product="I",
                    validity="DAY",
                    price=0,
                    instrument_token=position['instrument_key'],
                    order_type="MARKET",
                    transaction_type="SELL",
                    tag="mean_reversion_exit"
                )
                self.order_manager.close_paper_position(position['instrument_key'])
                del open_positions[instrument_key]
        else:
            # Enter a new position if the price has stretched away from the EVWMA
            score = 0
            if price > evwma_5m * 1.01: # 1% above EVWMA
                score = -1
            elif price < evwma_5m * 0.99: # 1% below EVWMA
                score = 1

            if score != 0:
                transaction_type = "BUY"
                # Find the ATM strike and the corresponding instrument key
                atm_strike = find_atm_strike(price)
                option_instrument_key = None

                for item in kwargs.get('option_chain'):
                    if hasattr(item, 'strike_price') and item.strike_price == atm_strike:
                        if score > 0 and hasattr(item, 'call_options'):
                            option_instrument_key = item.call_options.instrument_key
                            break
                        elif score < 0 and hasattr(item, 'put_options'):
                            option_instrument_key = item.put_options.instrument_key
                            break

                if not option_instrument_key:
                    logging.warning(f"Could not find ATM option for {instrument_key}. Skipping trade.")
                    return

                vpa_signal = kwargs.get('vpa_signal')
                logging.info(f"Placing Mean Reversion trade for {instrument_key}. Price: {price}, EVWMA_5m: {evwma_5m}, VPA: {vpa_signal}")
                trade_logger.info(f"ENTRY: Mean Reversion, {instrument_key}, {transaction_type}, {price}, EVWMA_5m: {evwma_5m}, {vpa_signal}")
                order_response = self.order_manager.place_order(
                    quantity=1,
                    product="I",
                    validity="DAY",
                    price=0,
                    instrument_token=option_instrument_key,
                    order_type="MARKET",
                    transaction_type=transaction_type,
                    tag="mean_reversion"
                )

                if order_response:
                    df = calculate_atr(kwargs.get('df'))
                    atr = df['atr'].iloc[-1]
                    direction = 'BULL' if score > 0 else 'BEAR'
                    last_swing = find_recent_swing(df, direction)
                    stop_loss_price = calculate_stop_loss(atr, "Scalp", last_swing, direction) # Using Scalp ATR multiplier

                    self.order_manager.place_gtt_order(
                        instrument_token=option_instrument_key,
                        transaction_type="SELL" if transaction_type == "BUY" else "BUY",
                        trigger_price=stop_loss_price,
                        price=stop_loss_price - 1,
                        quantity=1
                    )

                    open_positions[instrument_key] = {
                        'order_id': order_response.order_id,
                        'instrument_key': option_instrument_key,
                        'transaction_type': transaction_type,
                        'entry_price': price,
                        'stop_loss_price': stop_loss_price,
                        'direction': 'BULL' if score > 0 else 'BEAR'
                    }

def calculate_pcr(option_chain):
    """
    Calculates the Put-Call Ratio (PCR) from the option chain data.
    """
    total_put_oi = 0
    total_call_oi = 0
    for item in option_chain:
        if hasattr(item, 'put_options') and hasattr(item.put_options, 'open_interest'):
            total_put_oi += item.put_options.open_interest
        if hasattr(item, 'call_options') and hasattr(item.call_options, 'open_interest'):
            total_call_oi += item.call_options.open_interest

    if total_call_oi == 0:
        return 0

    return total_put_oi / total_call_oi

def calculate_evwma(df, length=20):
    """
    Calculates the Elastic Volume Weighted Moving Average (EVWMA) and its slope.
    """
    df['evwma'] = ta.vwma(df['high'], df['low'], df['close'], df['volume'], length=length)

    # Calculate the slope of the EVWMA
    df['evwma_slope'] = df['evwma'].diff()

    return df

def calculate_microstructure_score(price, evwma_1m, evwma_5m, evwma_1m_slope, evwma_5m_slope):
    """
    Calculates the Microstructure Confluence Score.
    """
    score = 0

    # dyn5: Direction of price vs. 5m EVWMA
    if price > evwma_5m:
        score += 5
    elif price < evwma_5m:
        score -= 5

    # dyn1: Direction of price vs. 1m EVWMA
    if price > evwma_1m:
        score += 1
    elif price < evwma_1m:
        score -= 1

    # evm5: Slope/Momentum of the 5m EVWMA
    if evwma_5m_slope > 0:
        score += 5
    elif evwma_5m_slope < 0:
        score -= 5

    # evm1: Slope/Momentum of the 1m EVWMA
    if evwma_1m_slope > 0:
        score += 1
    elif evwma_1m_slope < 0:
        score -= 1

    return score

def calculate_stop_loss(atr, trade_type, last_swing, direction):
    """
    Calculates the stop-loss based on ATR, trade type, and the last swing.
    """
    multipliers = {
        "Scalp": 0.7,
        "Hunter": 1.2,
        "P2P Trend": 1.5,
    }
    multiplier = multipliers.get(trade_type, 1.0)
    volatility_buffer = multiplier * atr

    # The stop-loss is placed slightly beyond the last swing
    if direction == "BULL":
        stop_loss = last_swing - volatility_buffer
    else: # BEAR
        stop_loss = last_swing + volatility_buffer

    return stop_loss

def calculate_probability_score(pcr_alignment, index_sync, score_force, value_area):
    """
    Calculates the probability score for a trade.
    """
    score = 0
    if pcr_alignment:
        score += 20
    if index_sync:
        score += 30
    if score_force:
        score += 30
    if value_area:
        score += 20
    return score

def calculate_atr(df, length=14):
    """
    Calculates the Average True Range (ATR).
    """
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=length)
    return df

def find_recent_swing(df, direction, n=20):
    """
    Finds the most recent swing high or low from the last n candles based on the trade direction.
    """
    df_slice = df.iloc[-n:]
    if direction == 'BULL':
        return df_slice['low'].min()
    else: # BEAR
        return df_slice['high'].max()

def detect_pocket_pivot_volume(df, lookback=10):
    """
    Detects Pocket Pivot Volume (PPV).
    """
    latest_bar = df.iloc[-1]
    if latest_bar['close'] <= latest_bar['open']:
        return False

    lookback_df = df.iloc[-lookback-1:-1]
    down_volume = lookback_df[lookback_df['close'] < lookback_df['open']]['volume']

    if down_volume.empty:
        return False

    return latest_bar['volume'] > down_volume.max()

def detect_pivot_negative_volume(df, lookback=10):
    """
    Detects Pivot Negative Volume (PNV).
    """
    latest_bar = df.iloc[-1]
    if latest_bar['close'] >= latest_bar['open']:
        return False

    lookback_df = df.iloc[-lookback-1:-1]
    up_volume = lookback_df[lookback_df['close'] > lookback_df['open']]['volume']

    if up_volume.empty:
        return False

    return latest_bar['volume'] > up_volume.max()

def detect_accumulation(df):
    """
    Detects accumulation.
    """
    latest_bar = df.iloc[-1]
    range = latest_bar['high'] - latest_bar['low']
    avg_range = (df['high'] - df['low']).mean()
    avg_volume = df['volume'].mean()

    return latest_bar['volume'] > avg_volume * 1.5 and range < avg_range * 0.7 and latest_bar['close'] > latest_bar['open']

def detect_distribution(df):
    """
    Detects distribution.
    """
    latest_bar = df.iloc[-1]
    range = latest_bar['high'] - latest_bar['low']
    avg_range = (df['high'] - df['low']).mean()
    avg_volume = df['volume'].mean()

    return latest_bar['volume'] > avg_volume * 1.5 and range < avg_range * 0.7 and latest_bar['close'] < latest_bar['open']
