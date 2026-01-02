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

    def test_on_message_candle_aggregation_new(self):
        # Arrange
        message = {
            'feeds': {
                'TEST_KEY': {
                    'ff': {
                        'marketFF': {
                            'ltpc': {
                                'ltp': 100,
                                'ltq': 50
                            }
                        }
                    }
                }
            }
        }

        # Act
        self.bot._on_message(message)

        # Assert
        self.assertIn('TEST_KEY', self.bot.one_minute_candles)
        self.assertEqual(self.bot.one_minute_candles['TEST_KEY']['open'], 100)
        self.assertEqual(self.bot.one_minute_candles['TEST_KEY']['volume'], 50)

    def test_on_message_candle_aggregation_update(self):
        # Arrange
        initial_message = {
            'feeds': {
                'TEST_KEY': {
                    'ff': {
                        'marketFF': {
                            'ltpc': {
                                'ltp': 100,
                                'ltq': 50
                            }
                        }
                    }
                }
            }
        }
        update_message = {
            'feeds': {
                'TEST_KEY': {
                    'ff': {
                        'marketFF': {
                            'ltpc': {
                                'ltp': 105,
                                'ltq': 75
                            }
                        }
                    }
                }
            }
        }
        self.bot._on_message(initial_message)

        # Act
        self.bot._on_message(update_message)

        # Assert
        candle = self.bot.one_minute_candles['TEST_KEY']
        self.assertEqual(candle['high'], 105)
        self.assertEqual(candle['close'], 105)
        self.assertEqual(candle['volume'], 125) # 50 + 75

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
        self.bot.execute_strategy('TEST_KEY', df)

        # Assert
        self.bot.strategies[DayType.BEARISH_TREND].execute.assert_called_once()
        config.USE_ADVANCED_VOLUME_ANALYSIS = True


if __name__ == '__main__':
    unittest.main()
