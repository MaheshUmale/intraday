import unittest
from unittest.mock import MagicMock, patch
from trading_bot.execution.execution import OrderManager
import trading_bot.config as config

class TestOrderManager(unittest.TestCase):
    def setUp(self):
        self.mock_api_client = MagicMock()
        self.order_manager = OrderManager(self.mock_api_client)

    def test_place_order_paper_trading(self):
        # Arrange
        config.PAPER_TRADING = True

        # Act
        response = self.order_manager.place_order(1, "I", "DAY", 0, "TEST_TOKEN", "MARKET", "BUY")

        # Assert
        self.assertIsNotNone(response.order_id)
        self.assertIn("TEST_TOKEN", self.order_manager.paper_positions)

    @patch('upstox_client.OrderApi')
    def test_place_order_live(self, mock_order_api):
        # Arrange
        config.PAPER_TRADING = False
        mock_order_api.return_value.place_order.return_value = "Success"

        # Act
        response = self.order_manager.place_order(1, "I", "DAY", 0, "TEST_TOKEN", "MARKET", "BUY")

        # Assert
        self.assertEqual(response, "Success")
        mock_order_api.return_value.place_order.assert_called_once()

    def test_modify_order_paper_trading(self):
        # Arrange
        config.PAPER_TRADING = True

        # Act
        response = self.order_manager.modify_order("some_id", 1, "DAY", 0, "MARKET")

        # Assert
        self.assertTrue(response)

    def test_cancel_order_paper_trading(self):
        # Arrange
        config.PAPER_TRADING = True

        # Act
        response = self.order_manager.cancel_order("some_id")

        # Assert
        self.assertTrue(response)

if __name__ == '__main__':
    unittest.main()
