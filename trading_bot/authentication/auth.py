import os
import logging
from dotenv import load_dotenv, set_key
import upstox_client
from upstox_client.rest import ApiException

class UpstoxAuthenticator:
    """
    Handles the authentication process for the Upstox API.
    """
    def __init__(self):
        """
        Initializes the UpstoxAuthenticator.
        """
        load_dotenv()
        self.api_client = None
        self.api_version = "v2"
        self.client_id = os.getenv("UPSTOX_API_KEY")
        self.client_secret = os.getenv("UPSTOX_API_SECRET")
        self.redirect_uri = os.getenv("UPSTOX_REDIRECT_URI")

    def _save_credentials(self, access_token):
        """
        Saves the access token to the .env file.
        """
        dotenv_path = '.env'
        set_key(dotenv_path, "UPSTOX_ACCESS_TOKEN", access_token)
        logging.info("Access token saved to .env file.")

    def get_api_client(self):
        """
        Authenticates the user and returns an API client instance.
        """
        access_token = os.getenv("UPSTOX_ACCESS_TOKEN")

        if access_token:
            self.api_client = self._configure_api_client(access_token)
            if self._is_token_valid():
                logging.info("Access token is valid.")
                return self.api_client
            else:
                logging.info("Access token has expired. Refreshing token...")
                return self._refresh_token()
        else:
            return self._login_and_get_client()

    def _configure_api_client(self, access_token):
        """
        Configures the API client with the given access token.
        """
        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        return upstox_client.ApiClient(configuration)

    def _is_token_valid(self):
        """
        Checks if the current access token is valid by making a test API call.
        """
        try:
            profile_api = upstox_client.UserApi(self.api_client)
            profile_api.get_profile(self.api_version)
            return True
        except ApiException as e:
            logging.warning(f"Token validation failed with status: {e.status}")
            return False

    def _login_and_get_client(self):
        """
        Performs the login flow to get a new access token.
        """
        api_instance = upstox_client.LoginApi()
        api_instance.redirect_uri = self.redirect_uri

        try:
            # Generate the authorization URL
            login_url = api_instance.authorise(self.client_id, self.api_version)
            print(f"Please login to this URL: {login_url}")

            # Get the authorization code from the user
            auth_code = input("Enter the authorization code: ")

            # Get the access token
            api_instance.client_id = self.client_id
            api_instance.client_secret = self.client_secret

            token_response = api_instance.token(
                self.api_version,
                code=auth_code,
                grant_type="authorization_code"
            )

            access_token = token_response.access_token
            self._save_credentials(access_token)

            return self._configure_api_client(access_token)
        except ApiException as e:
            logging.error(f"Exception when calling LoginApi->token: {e}")
            return None

    def _refresh_token(self):
        """
        Refreshes the access token using the refresh token.
        This part is a placeholder as the upstox-python-sdk does not directly support token refresh.
        A manual implementation would be needed here.
        For now, it will just re-trigger the login process.
        """
        logging.warning("Token refresh mechanism is not fully implemented in the SDK. Re-initiating login.")
        return self._login_and_get_client()
