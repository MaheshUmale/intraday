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
            probability_score = calculate_probability_score(
                pcr_alignment=pcr_alignment,
                index_sync=True, # Placeholder
                score_force=abs(score) > 10,
                value_area=True # Placeholder
            )

            if probability_score < config.PROBABILITY_THRESHOLD:
                logging.info(f"Probability score {probability_score} is below threshold. Skipping trade.")
                return

            transaction_type = "BUY" if score > 0 else "SELL"

            # Find the ATM strike and the corresponding instrument key
            atm_strike = find_atm_strike(price)
            option_instrument_key = None

            for item in option_chain:
                if hasattr(item, 'strike_price') and item.strike_price == atm_strike:
                    if transaction_type == "BUY" and hasattr(item, 'call_options'):
                        option_instrument_key = item.call_options.instrument_key
                        break
                    elif transaction_type == "SELL" and hasattr(item, 'put_options'):
                        option_instrument_key = item.put_options.instrument_key
                        break

            if not option_instrument_key:
                logging.warning(f"Could not find ATM option for {instrument_key}. Skipping trade.")
                return

            # Place a market order
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
                last_swing = find_recent_swing(df)
                stop_loss_price = calculate_stop_loss(atr, "Hunter", last_swing, transaction_type)

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
                    'stop_loss_price': stop_loss_price
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
            # Hold the position until the score flips
            if (score > 0 and open_positions[instrument_key]['transaction_type'] == "SELL") or \
               (score < 0 and open_positions[instrument_key]['transaction_type'] == "BUY"):
                logging.info(f"Score flipped for {instrument_key}. Closing position.")
                # (Implement logic to close the position)
                del open_positions[instrument_key]
        elif abs(score) >= config.SCORE_THRESHOLD:
            # Enter a new position
            transaction_type = "BUY" if score > 0 else "SELL"

            # Find the ATM strike and the corresponding instrument key
            atm_strike = find_atm_strike(price)
            option_instrument_key = None

            for item in kwargs.get('option_chain'):
                if hasattr(item, 'strike_price') and item.strike_price == atm_strike:
                    if transaction_type == "BUY" and hasattr(item, 'call_options'):
                        option_instrument_key = item.call_options.instrument_key
                        break
                    elif transaction_type == "SELL" and hasattr(item, 'put_options'):
                        option_instrument_key = item.put_options.instrument_key
                        break

            if not option_instrument_key:
                logging.warning(f"Could not find ATM option for {instrument_key}. Skipping trade.")
                return

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
                last_swing = find_recent_swing(df)
                stop_loss_price = calculate_stop_loss(atr, "P2P Trend", last_swing, transaction_type)

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
                    'stop_loss_price': stop_loss_price
                }

class Scalp(TacticalTemplate):
    def execute(self, **kwargs):
        # Implementation of the Scalp logic
        pass

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
            # Close the position if the price has reverted to the mean
            if (open_positions[instrument_key]['transaction_type'] == "BUY" and price >= evwma_1m) or \
               (open_positions[instrument_key]['transaction_type'] == "SELL" and price <= evwma_1m):
                logging.info(f"Price reverted for {instrument_key}. Closing position.")
                # (Implement logic to close the position)
                del open_positions[instrument_key]
        else:
            # Enter a new position if the price has stretched away from the EVWMA
            transaction_type = None
            if price > evwma_5m * 1.01: # 1% above EVWMA
                transaction_type = "SELL"
            elif price < evwma_5m * 0.99: # 1% below EVWMA
                transaction_type = "BUY"

            if transaction_type:
                # Find the ATM strike and the corresponding instrument key
                atm_strike = find_atm_strike(price)
                option_instrument_key = None

                for item in kwargs.get('option_chain'):
                    if hasattr(item, 'strike_price') and item.strike_price == atm_strike:
                        if transaction_type == "BUY" and hasattr(item, 'call_options'):
                            option_instrument_key = item.call_options.instrument_key
                            break
                        elif transaction_type == "SELL" and hasattr(item, 'put_options'):
                            option_instrument_key = item.put_options.instrument_key
                            break

                if not option_instrument_key:
                    logging.warning(f"Could not find ATM option for {instrument_key}. Skipping trade.")
                    return

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
                    last_swing = find_recent_swing(df)
                    stop_loss_price = calculate_stop_loss(atr, "Scalp", last_swing, transaction_type) # Using Scalp ATR multiplier

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
                        'stop_loss_price': stop_loss_price
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

def calculate_stop_loss(atr, trade_type, last_swing, transaction_type):
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
    if transaction_type == "BUY":
        stop_loss = last_swing - volatility_buffer
    else: # SELL
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

def find_recent_swing(df, n=20):
    """
    Finds the most recent swing high or low from the last n candles.
    """
    df_slice = df.iloc[-n:]
    swing_high = df_slice['high'].max()
    swing_low = df_slice['low'].min()

    # Determine if the most recent swing was a high or a low
    if df_slice['high'].idxmax() > df_slice['low'].idxmin():
        return swing_high
    else:
        return swing_low
