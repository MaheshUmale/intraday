import unittest
from unittest.mock import patch
from trading_bot.authentication.auth import UpstoxAuthenticator
import os
import upstox_client

class TestUpstoxAuthenticator(unittest.TestCase):
    @patch.dict(os.environ, {'UPSTOX_ACCESS_TOKEN': 'test_token'})
    def test_get_api_client_with_token(self):
        """
        Tests that the API client is returned when a token is present.
        """
        # Arrange
        authenticator = UpstoxAuthenticator()

        # Act
        api_client = authenticator.get_api_client()

        # Assert
        self.assertIsNotNone(api_client)
        self.assertIsInstance(api_client, upstox_client.ApiClient)

    @patch.dict(os.environ, {}, clear=True)
    def test_get_api_client_without_token(self):
        """
        Tests that None is returned when the access token is missing.
        """
        # Arrange
        authenticator = UpstoxAuthenticator()

        # Act
        api_client = authenticator.get_api_client()

        # Assert
        self.assertIsNone(api_client)

if __name__ == '__main__':
    unittest.main()
