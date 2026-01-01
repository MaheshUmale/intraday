import upstox_client
from upstox_client.rest import ApiException
import logging

import trading_bot.config as config

class OrderManager:
    def __init__(self, api_client):
        self.api_client = api_client
        self.order_api = upstox_client.OrderApiV3(self.api_client)
        self.paper_portfolio = {}

    def place_order(self, quantity, product, validity, price, instrument_token, order_type, transaction_type, disclosed_quantity=0, trigger_price=0.0, is_amo=False):
        """
        Places an order with the Upstox API V3.
        """
        body = upstox_client.PlaceOrderV3Request(
            quantity=quantity,
            product=product,
            validity=validity,
            price=price,
            tag=instrument_token,
            instrument_token=instrument_token,
            order_type=order_type,
            transaction_type=transaction_type,
            disclosed_quantity=disclosed_quantity,
            trigger_price=trigger_price,
            is_amo=is_amo
        )
        try:
            # The 'algo_name' parameter is optional, as seen in the SDK docs.
            if config.PAPER_TRADING:
                logging.info(f"PAPER TRADE: {transaction_type} {quantity} of {instrument_token} at {price}")
                self.paper_portfolio[instrument_token] = {
                    "quantity": quantity,
                    "transaction_type": transaction_type,
                    "entry_price": price
                }
                return { "status": "success", "order_id": "dummy_order_id" }
            else:
                api_response = self.order_api.place_order(body=body, api_version="v3")
                logging.info(f"Order placed successfully: {api_response}")
                return api_response
        except ApiException as e:
            logging.error(f"Exception when calling OrderApiV3->place_order: {e}", exc_info=True)
            return None

    def get_paper_positions(self):
        """
        Returns the paper trading positions.
        """
        return self.paper_portfolio

    def modify_order(self, order_id, quantity, validity, price, order_type, trigger_price=0.0):
        """
        Modifies an existing order using API V3.
        """
        body = upstox_client.ModifyOrderRequest(
            quantity=quantity,
            validity=validity,
            price=price,
            order_id=order_id,
            order_type=order_type,
            trigger_price=trigger_price
        )
        try:
            api_response = self.order_api.modify_order(body=body, api_version="v3")
            logging.info(f"Order modified successfully: {api_response}")
            return api_response
        except ApiException as e:
            logging.error(f"Exception when calling OrderApiV3->modify_order: {e}", exc_info=True)
            return None

    def cancel_order(self, order_id):
        """
        Cancels an existing order using API V3.
        """
        try:
            # For V3, the order_id is passed directly as a parameter.
            api_response = self.order_api.cancel_order(order_id=order_id, api_version="v3")
            logging.info(f"Order cancelled successfully: {api_response}")
            return api_response
        except ApiException as e:
            logging.error(f"Exception when calling OrderApiV3->cancel_order: {e}", exc_info=True)
            return None

    def place_gtt_order(self, instrument_token, transaction_type, trigger_price, price, quantity):
        """
        Places a GTT (Good Till Triggered) order.
        """
        logging.info(f"DUMMY GTT ORDER: instrument_token={instrument_token}, transaction_type={transaction_type}, trigger_price={trigger_price}, price={price}, quantity={quantity}")
        return { "status": "success", "order_id": "dummy_gtt_order_id" }
