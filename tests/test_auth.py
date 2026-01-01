import unittest
from unittest.mock import Mock, patch, call
from trading_bot.authentication.auth import UpstoxAuthenticator
import os

class TestAuth(unittest.TestCase):

    def setUp(self):
        self.authenticator = UpstoxAuthenticator()

    @patch('builtins.open')
    def test_store_tokens(self, mock_open):
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file

        mock_api_response = Mock()
        mock_api_response.access_token = "test_access_token"
        mock_api_response.refresh_token = "test_refresh_token"

        self.authenticator._store_tokens(mock_api_response)

        # Check that the tokens are written to the .env file
        calls = [
            call("UPSTOX_ACCESS_TOKEN='test_access_token'\n"),
            call("UPSTOX_REFRESH_TOKEN='test_refresh_token'\n")
        ]
        mock_file.write.assert_has_calls(calls, any_order=True)

        # Check that the environment variables are set
        self.assertEqual(os.environ["UPSTOX_ACCESS_TOKEN"], "test_access_token")
        self.assertEqual(os.environ["UPSTOX_REFRESH_TOKEN"], "test_refresh_token")

if __name__ == '__main__':
    unittest.main()
