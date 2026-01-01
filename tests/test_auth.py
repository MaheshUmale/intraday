import unittest
from unittest.mock import Mock, patch, call
from trading_bot.authentication.auth import UpstoxAuthenticator
import os

class TestAuth(unittest.TestCase):

    def setUp(self):
        self.authenticator = UpstoxAuthenticator()

    @patch('trading_bot.authentication.auth.set_key')
    @patch.dict(os.environ, {}, clear=True)
    def test_store_tokens(self, mock_set_key):
        mock_api_response = Mock()
        mock_api_response.access_token = "test_access_token"
        mock_api_response.refresh_token = "test_refresh_token"

        self.authenticator._store_tokens(mock_api_response)

        # Check that set_key was called with the correct arguments
        calls = [
            call(".env", "UPSTOX_ACCESS_TOKEN", "test_access_token"),
            call(".env", "UPSTOX_REFRESH_TOKEN", "test_refresh_token")
        ]
        mock_set_key.assert_has_calls(calls, any_order=True)

        # Check that the environment variables are set
        self.assertEqual(os.environ["UPSTOX_ACCESS_TOKEN"], "test_access_token")
        self.assertEqual(os.environ["UPSTOX_REFRESH_TOKEN"], "test_refresh_token")

if __name__ == '__main__':
    unittest.main()
