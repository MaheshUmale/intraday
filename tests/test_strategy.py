import unittest
from unittest.mock import MagicMock
import pandas as pd
from trading_bot.strategy.strategy import (
    classify_day_type, DayType, calculate_microstructure_score,
    calculate_stop_loss, calculate_pcr, detect_pocket_pivot_volume
)

class TestStrategy(unittest.TestCase):
    def test_classify_day_type(self):
        # Bullish Trend
        self.assertEqual(classify_day_type(105, 100, 90, 1.3), DayType.BULLISH_TREND)
        # Bearish Trend
        self.assertEqual(classify_day_type(85, 100, 90, 0.6), DayType.BEARISH_TREND)
        # Sideways Bull Trap
        self.assertEqual(classify_day_type(105, 100, 90, 0.8), DayType.SIDEWAYS_BULL_TRAP)
        # Sideways Bear Trap
        self.assertEqual(classify_day_type(85, 100, 90, 1.2), DayType.SIDEWAYS_BEAR_TRAP)
        # Sideways/Choppy
        self.assertEqual(classify_day_type(95, 100, 90, 1.0), DayType.SIDEWAYS_CHOPPY)

    def test_calculate_microstructure_score(self):
        # Strong bullish
        score = calculate_microstructure_score(105, 102, 100, 1, 1)
        self.assertEqual(score, 12)
        # Strong bearish
        score = calculate_microstructure_score(95, 98, 100, -1, -1)
        self.assertEqual(score, -12)
        # Neutral
        score = calculate_microstructure_score(100, 100, 100, 0, 0)
        self.assertEqual(score, 0)

    def test_calculate_stop_loss(self):
        # Bullish trade
        stop_loss = calculate_stop_loss(2, "Hunter", 100, "BULL", 105)
        self.assertLess(stop_loss, 100)
        # Bearish trade
        stop_loss = calculate_stop_loss(2, "Hunter", 100, "BEAR", 95)
        self.assertGreater(stop_loss, 100)

    def test_calculate_pcr(self):
        # Mocking the OptionStrikeData objects with the correct nested structure
        mock_strike_1 = MagicMock()
        mock_strike_1.put_options.market_data.open_interest = 100
        mock_strike_1.call_options.market_data.open_interest = 50

        mock_strike_2 = MagicMock()
        mock_strike_2.put_options.market_data.open_interest = 200
        mock_strike_2.call_options.market_data.open_interest = 100

        option_chain = [mock_strike_1, mock_strike_2]
        pcr = calculate_pcr(option_chain)
        self.assertEqual(pcr, (100 + 200) / (50 + 100))

    def test_detect_pocket_pivot_volume(self):
        data = {
            'open': [100, 102, 101, 103, 105, 104, 106, 105, 107, 108, 110],
            'close': [101, 101, 102, 104, 104, 105, 105, 106, 108, 109, 112],
            'volume': [10, 12, 15, 8, 9, 11, 7, 13, 6, 14, 20]
        }
        df = pd.DataFrame(data)
        # Last bar has high volume on up close
        is_ppv = detect_pocket_pivot_volume(df)
        self.assertTrue(is_ppv)
        # Last bar has low volume
        df.loc[10, 'volume'] = 5
        is_ppv = detect_pocket_pivot_volume(df)
        self.assertFalse(is_ppv)

if __name__ == '__main__':
    unittest.main()
