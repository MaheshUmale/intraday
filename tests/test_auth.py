import unittest
from unittest.mock import patch, MagicMock
from trading_bot.authentication.auth import UpstoxAuthenticator
import os

class TestUpstoxAuthenticator(unittest.TestCase):
    @patch('trading_bot.authentication.auth.load_dotenv')
    @patch('trading_bot.authentication.auth.set_key')
    @patch('upstox_client.Configuration')
    @patch('upstox_client.ApiClient')
    @patch('upstox_client.UserApi')
    def test_get_api_client_with_valid_token(self, mock_user_api, mock_api_client, mock_configuration, mock_set_key, mock_load_dotenv):
        # Arrange
        with patch.dict(os.environ, {'UPSTOX_ACCESS_TOKEN': 'valid_token'}):
            mock_user_api.return_value.get_profile.return_value = True # Simulate a successful API call
            authenticator = UpstoxAuthenticator()

            # Act
            api_client = authenticator.get_api_client()

            # Assert
            self.assertIsNotNone(api_client)
            mock_user_api.return_value.get_profile.assert_called_once()
            mock_load_dotenv.assert_called_once()

    @patch('trading_bot.authentication.auth.load_dotenv')
    @patch('trading_bot.authentication.auth.set_key')
    @patch('upstox_client.LoginApi')
    @patch('builtins.input', return_value='test_auth_code')
    def test_login_and_get_client(self, mock_input, mock_login_api, mock_set_key, mock_load_dotenv):
        # Arrange
        mock_token_response = MagicMock()
        mock_token_response.access_token = 'new_access_token'
        mock_login_api.return_value.token.return_value = mock_token_response
        authenticator = UpstoxAuthenticator()

        # Act
        api_client = authenticator._login_and_get_client()

        # Assert
        self.assertIsNotNone(api_client)
        mock_set_key.assert_called_once_with('.env', "UPSTOX_ACCESS_TOKEN", 'new_access_token')
        mock_load_dotenv.assert_called_once()

if __name__ == '__main__':
    unittest.main()
