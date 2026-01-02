import logging
import trading_bot.config as config
import upstox_client
from upstox_client.rest import ApiException
import uuid
from datetime import datetime

class OrderManager:
    """
    Manages order placement, modification, and cancellation.
    """
    def __init__(self, api_client):
        """
        Initializes the OrderManager.
        """
        self.api_client = api_client
        self.paper_positions = {}
        self.paper_trades = [] # To store closed trades for analysis

    def place_order(self, quantity, product, validity, price, instrument_token, order_type, transaction_type, tag=None, timestamp=None):
        """
        Places an order.
        """
        if config.PAPER_TRADING:
            order_id = str(uuid.uuid4())
            entry_time = timestamp if timestamp else datetime.now()
            logging.info(f"PAPER TRADING: Placing {transaction_type} {order_type} order for {instrument_token}.")
            self.paper_positions[instrument_token] = {
                'order_id': order_id,
                'instrument_key': instrument_token,
                'transaction_type': transaction_type,
                'entry_price': price, # In a real scenario, this would be the fill price
                'entry_time': entry_time,
                'stop_loss_price': 0, # To be updated later
                'direction': 'BULL' if transaction_type == 'BUY' else 'BEAR'
            }
            # Mock a successful order response object
            class MockOrderResponse:
                def __init__(self):
                    self.order_id = order_id
            return MockOrderResponse()

        try:
            order_api = upstox_client.OrderApiV3(self.api_client)
            body = upstox_client.PlaceOrderV3Request(
                quantity=quantity,
                product=product,
                validity=validity,
                price=price,
                instrument_token=instrument_token,
                order_type=order_type,
                transaction_type=transaction_type,
                disclosed_quantity=0,
                trigger_price=0.0,
                is_amo=False,
                tag=tag
            )
            order_response = order_api.place_order(body=body)
            logging.info(f"Order placed successfully: {order_response}")
            return order_response
        except ApiException as e:
            logging.error(f"Exception when calling OrderApiV3->place_order: {e}")
            return None

    def modify_order(self, order_id, quantity, validity, price, order_type, trigger_price=0):
        """
        Modifies an existing order.
        """
        if config.PAPER_TRADING:
            logging.info(f"PAPER TRADING: Modifying order {order_id}.")
            return True

        try:
            order_api = upstox_client.OrderApiV3(self.api_client)
            body = upstox_client.ModifyOrderV3Request(
                quantity=quantity,
                validity=validity,
                price=price,
                order_id=order_id,
                order_type=order_type,
                trigger_price=trigger_price
            )
            order_response = order_api.modify_order(body=body)
            logging.info(f"Order modified successfully: {order_response}")
            return order_response
        except ApiException as e:
            logging.error(f"Exception when calling OrderApiV3->modify_order: {e}")
            return None

    def cancel_order(self, order_id):
        """
        Cancels an existing order.
        """
        if config.PAPER_TRADING:
            logging.info(f"PAPER TRADING: Cancelling order {order_id}.")
            return True

        try:
            order_api = upstox_client.OrderApiV3(self.api_client)
            order_response = order_api.cancel_order(order_id=order_id)
            logging.info(f"Order cancelled successfully: {order_response}")
            return order_response
        except ApiException as e:
            logging.error(f"Exception when calling OrderApiV3->cancel_order: {e}")
            return None

    def place_gtt_order(self, instrument_token, transaction_type, trigger_price, price, quantity):
        """
        Places a Good Till Triggered (GTT) order.
        """
        if config.PAPER_TRADING:
            logging.info(f"PAPER TRADING: Placing GTT {transaction_type} order for {instrument_token} at trigger price {trigger_price}.")
            if instrument_token in self.paper_positions:
                self.paper_positions[instrument_token]['stop_loss_price'] = trigger_price
            return True

        try:
            order_api = upstox_client.OrderApiV3(self.api_client)
            triggered_order = upstox_client.GttOrderV3(
                transaction_type=transaction_type,
                product="I",
                order_type="LIMIT",
                quantity=quantity,
                price=price
            )
            condition = upstox_client.GttConditionV3(
                trigger_values=[trigger_price],
                instrument_token=instrument_token
            )
            body = upstox_client.PlaceGttOrderV3Request(
                condition=condition,
                orders=[triggered_order]
            )
            order_response = order_api.place_gtt_order(body=body)
            logging.info(f"GTT Order placed successfully: {order_response}")
            return order_response
        except ApiException as e:
            logging.error(f"Exception when calling OrderApiV3->place_gtt_order: {e}")
            return None

    def get_paper_positions(self):
        """
        Returns the current paper trading positions.
        """
        return self.paper_positions

    def close_paper_position(self, instrument_key, exit_price, exit_time):
        """
        Closes a paper position and records the trade.
        """
        if instrument_key in self.paper_positions:
            position = self.paper_positions[instrument_key]

            # Calculate PnL
            if position['direction'] == 'BULL': # Long position
                pnl = exit_price - position['entry_price']
            else: # Short position
                pnl = position['entry_price'] - exit_price

            # Create a trade record
            trade = {
                'instrument_key': position['instrument_key'],
                'entry_price': position['entry_price'],
                'exit_price': exit_price,
                'pnl': pnl,
                'entry_time': position['entry_time'],
                'exit_time': exit_time,
                'direction': position['direction']
            }
            self.paper_trades.append(trade)

            logging.info(f"Paper position closed for {instrument_key}. PnL: {pnl:.2f}")
            del self.paper_positions[instrument_key]

    def get_all_paper_trades(self):
        """
        Returns all closed paper trades.
        """
        return self.paper_trades
