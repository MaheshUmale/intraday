import unittest
from unittest.mock import patch, MagicMock
from trading_bot.main import TradingBot
import pandas as pd
from trading_bot.strategy.strategy import DayType
import trading_bot.config as config

class TestTradingBot(unittest.TestCase):
    def setUp(self):
        self.bot = TradingBot()
        # Mock dependencies
        self.bot.data_handler = MagicMock()
        self.bot.order_manager = MagicMock()
        self.bot.strategies = {DayType.BEARISH_TREND: MagicMock()}

    @patch('trading_bot.main.classify_day_type')
    @patch('trading_bot.main.calculate_pcr')
    @patch('trading_bot.main.calculate_microstructure_score')
    @patch('pandas_ta.vwma')
    def test_execute_strategy(self, mock_vwma, mock_calc_score, mock_calc_pcr, mock_classify_day):
        # Arrange
        config.USE_ADVANCED_VOLUME_ANALYSIS = False
        self.bot.hunter_zone['TEST_KEY'] = {'high': 100, 'low': 90}
        df = pd.DataFrame({'open': [95], 'close': [98], 'high': [99], 'low': [94], 'volume': [1000], 'timestamp': [pd.Timestamp.now()]})
        mock_classify_day.return_value = DayType.BEARISH_TREND
        mock_calc_pcr.return_value = 0.8
        mock_calc_score.return_value = -10
        mock_vwma.return_value = pd.Series([100])

        # Act
        self.bot.execute_strategy('TEST_KEY', df, pd.Timestamp.now())

        # Assert
        self.bot.strategies[DayType.BEARISH_TREND].execute.assert_called_once()
        config.USE_ADVANCED_VOLUME_ANALYSIS = True

    @patch('trading_bot.main.TradingBot.execute_strategy')
    def test_fetch_and_process_candles(self, mock_execute_strategy):
        # Arrange
        self.bot.config.INSTRUMENTS = ['TEST_KEY']
        candle_data = [{'timestamp': '2024-01-01T10:00:00', 'open': 100, 'high': 105, 'low': 95, 'close': 102, 'volume': 1000, 'oi': 0}]
        self.bot.data_handler.get_intra_day_candle_data.return_value = candle_data

        # Act
        self.bot.fetch_and_process_candles()

        # Assert
        mock_execute_strategy.assert_called_once()
        self.assertEqual(self.bot.last_processed_timestamp['TEST_KEY'], pd.Timestamp('2024-01-01T10:00:00'))


if __name__ == '__main__':
    unittest.main()
