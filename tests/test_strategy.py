import unittest
from trading_bot.strategy.strategy import classify_day_type, calculate_microstructure_score, DayType, calculate_stop_loss, calculate_probability_score

class TestStrategy(unittest.TestCase):

    def test_classify_day_type(self):
        self.assertEqual(classify_day_type(10100, 10000, 9900, 1.3), DayType.BULLISH_TREND)
        self.assertEqual(classify_day_type(9800, 10000, 9900, 0.6), DayType.BEARISH_TREND)
        self.assertEqual(classify_day_type(10100, 10000, 9900, 0.8), DayType.SIDEWAYS_BULL_TRAP)
        self.assertEqual(classify_day_type(9800, 10000, 9900, 1.2), DayType.SIDEWAYS_BEAR_TRAP)
        self.assertEqual(classify_day_type(9950, 10000, 9900, 1.0), DayType.SIDEWAYS_CHOPPY)

    def test_calculate_microstructure_score(self):
        # Test case 1: Bullish
        self.assertEqual(calculate_microstructure_score(100, 90, 80, 1, 1), 12)

        # Test case 2: Bearish
        self.assertEqual(calculate_microstructure_score(80, 90, 100, -1, -1), -12)

        # Test case 3: Neutral
        self.assertEqual(calculate_microstructure_score(90, 90, 90, 0, 0), 0)

    def test_calculate_stop_loss(self):
        self.assertAlmostEqual(calculate_stop_loss(10, "Scalp", 100, "BUY"), 93.0)
        self.assertAlmostEqual(calculate_stop_loss(10, "Hunter", 100, "BUY"), 88.0)
        self.assertAlmostEqual(calculate_stop_loss(10, "P2P Trend", 100, "BUY"), 85.0)
        self.assertAlmostEqual(calculate_stop_loss(10, "Scalp", 100, "SELL"), 107.0)
        self.assertAlmostEqual(calculate_stop_loss(10, "Hunter", 100, "SELL"), 112.0)
        self.assertAlmostEqual(calculate_stop_loss(10, "P2P Trend", 100, "SELL"), 115.0)

    def test_calculate_probability_score(self):
        self.assertEqual(calculate_probability_score(True, True, True, True), 100)
        self.assertEqual(calculate_probability_score(False, False, False, False), 0)
        self.assertEqual(calculate_probability_score(True, False, True, False), 50)

if __name__ == '__main__':
    unittest.main()
