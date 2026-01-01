import unittest
from unittest.mock import Mock, patch
from trading_bot.execution.execution import OrderManager
import trading_bot.config as config
import logging

class TestExecution(unittest.TestCase):

    @patch('trading_bot.execution.execution.upstox_client.OrderApiV3')
    def setUp(self, MockOrderApiV3):
        self.mock_api_client = Mock()
        self.mock_order_api = MockOrderApiV3.return_value
        self.order_manager = OrderManager(self.mock_api_client)

    @patch('trading_bot.execution.execution.logging.info')
    def test_place_order_paper_trading(self, mock_logging_info):
        config.PAPER_TRADING = True
        self.order_manager.place_order(1, "I", "DAY", 0, "test_token", "MARKET", "BUY", "test_tag")
        mock_logging_info.assert_called_with("PAPER TRADE: BUY 1 of test_token at 0")
        self.mock_order_api.place_order.assert_not_called()

    def test_place_order_live_trading(self):
        config.PAPER_TRADING = False
        self.order_manager.place_order(1, "I", "DAY", 0, "test_token", "MARKET", "BUY", "test_tag")
        self.mock_order_api.place_order.assert_called_once()

    @patch('trading_bot.execution.execution.logging.info')
    def test_place_gtt_order_paper_trading(self, mock_logging_info):
        config.PAPER_TRADING = True
        self.order_manager.place_gtt_order("test_token", "SELL", 100, 99, 1)
        mock_logging_info.assert_called_with("DUMMY GTT ORDER: instrument_token=test_token, transaction_type=SELL, trigger_price=100, price=99, quantity=1")
        self.mock_order_api.place_gtt_order.assert_not_called()

    def test_modify_order(self):
        self.order_manager.modify_order("test_order_id", 1, "DAY", 0, "MARKET")
        self.mock_order_api.modify_order.assert_called_once()

    def test_cancel_order(self):
        self.order_manager.cancel_order("test_order_id")
        self.mock_order_api.cancel_order.assert_called_once()

if __name__ == '__main__':
    unittest.main()
