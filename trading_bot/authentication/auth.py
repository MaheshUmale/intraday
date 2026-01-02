import os
import logging
from dotenv import load_dotenv
import upstox_client

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

    def get_api_client(self):
        """
        Authenticates the user and returns an API client instance.
        """
        access_token = os.getenv("UPSTOX_ACCESS_TOKEN")

        if access_token:
            self.api_client = self._configure_api_client(access_token)
            logging.info("API client configured with access token.")
            return self.api_client
        else:
            logging.error("UPSTOX_ACCESS_TOKEN not found in .env file.")
            return None

    def _configure_api_client(self, access_token):
        """
        Configures the API client with the given access token.
        """
        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        return upstox_client.ApiClient(configuration)
