import logging
import trading_bot.config as config
import upstox_client
from upstox_client.rest import ApiException
import uuid

class OrderManager:
    """
    Manages order placement, modification, and cancellation.
    """
    def __init__(self, api_client):
        """
        Initializes the OrderManager.
        """
        self.api_client = api_client
        self.api_version = "v2"
        self.paper_positions = {}

    def place_order(self, quantity, product, validity, price, instrument_token, order_type, transaction_type, tag=None):
        """
        Places an order.
        """
        if config.PAPER_TRADING:
            order_id = str(uuid.uuid4())
            logging.info(f"PAPER TRADING: Placing {transaction_type} {order_type} order for {instrument_token}.")
            self.paper_positions[instrument_token] = {
                'order_id': order_id,
                'instrument_key': instrument_token,
                'transaction_type': transaction_type,
                'entry_price': price, # In a real scenario, this would be the fill price
                'stop_loss_price': 0, # To be updated later
                'direction': 'BULL' if transaction_type == 'BUY' else 'BEAR'
            }
            # Mock a successful order response object
            class MockOrderResponse:
                def __init__(self):
                    self.order_id = order_id
            return MockOrderResponse()

        try:
            order_api = upstox_client.OrderApi(self.api_client)
            order_response = order_api.place_order(
                self.api_version,
                upstox_client.PlaceOrderRequest(
                    quantity=quantity,
                    product=product,
                    validity=validity,
                    price=price,
                    instrument_token=instrument_token,
                    order_type=order_type,
                    transaction_type=transaction_type,
                    disclosed_quantity=0,
                    trigger_price=0,
                    is_amo=False,
                    tag=tag
                )
            )
            logging.info(f"Order placed successfully: {order_response}")
            return order_response
        except ApiException as e:
            logging.error(f"Exception when calling OrderApi->place_order: {e}")
            return None

    def modify_order(self, order_id, quantity, validity, price, order_type, trigger_price=0):
        """
        Modifies an existing order.
        """
        if config.PAPER_TRADING:
            logging.info(f"PAPER TRADING: Modifying order {order_id}.")
            return True

        try:
            order_api = upstox_client.OrderApi(self.api_client)
            order_response = order_api.modify_order(
                self.api_version,
                upstox_client.ModifyOrderRequest(
                    quantity=quantity,
                    validity=validity,
                    price=price,
                    order_id=order_id,
                    order_type=order_type,
                    trigger_price=trigger_price
                )
            )
            logging.info(f"Order modified successfully: {order_response}")
            return order_response
        except ApiException as e:
            logging.error(f"Exception when calling OrderApi->modify_order: {e}")
            return None

    def cancel_order(self, order_id):
        """
        Cancels an existing order.
        """
        if config.PAPER_TRADING:
            logging.info(f"PAPER TRADING: Cancelling order {order_id}.")
            return True

        try:
            order_api = upstox_client.OrderApi(self.api_client)
            order_response = order_api.cancel_order(self.api_version, order_id)
            logging.info(f"Order cancelled successfully: {order_response}")
            return order_response
        except ApiException as e:
            logging.error(f"Exception when calling OrderApi->cancel_order: {e}")
            return None

    def place_gtt_order(self, instrument_token, transaction_type, trigger_price, price, quantity):
        """
        Places a Good Till Triggered (GTT) order.
        NOTE: The upstox-python-sdk might not have a direct GTT placement method.
              This is a placeholder for the actual implementation.
        """
        if config.PAPER_TRADING:
            logging.info(f"PAPER TRADING: Placing GTT {transaction_type} order for {instrument_token} at trigger price {trigger_price}.")
            # In paper trading, we can simulate setting the stop-loss directly
            if instrument_token in self.paper_positions:
                self.paper_positions[instrument_token]['stop_loss_price'] = trigger_price
            return True

        logging.warning("GTT order placement is not implemented yet.")
        return None

    def get_paper_positions(self):
        """
        Returns the current paper trading positions.
        """
        return self.paper_positions

    def close_paper_position(self, instrument_key):
        """
        Removes a position from the paper trading portfolio.
        """
        if instrument_key in self.paper_positions:
            del self.paper_positions[instrument_key]
            logging.info(f"Paper position closed for {instrument_key}")
