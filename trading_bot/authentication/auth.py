import os
import upstox_client
from dotenv import load_dotenv
import logging

load_dotenv()

class UpstoxAuthenticator:
    def __init__(self):
        self.api_client = None
        self.api_instance = upstox_client.LoginApi()
        self.access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
        self.refresh_token = os.getenv("UPSTOX_REFRESH_TOKEN")
        self.client_id = os.getenv("UPSTOX_API_KEY")
        self.client_secret = os.getenv("UPSTOX_API_SECRET")
        self.redirect_uri = os.getenv("UPSTOX_REDIRECT_URI")
        self.api_version = "v2"

    def login(self):
        """
        Logs in to the Upstox API and returns an API client instance.
        """
        if self.access_token:
            self._create_api_client(self.access_token)
            return self.api_client

        # Generate the authorization URL
        response = self.api_instance.authorise(self.client_id, self.redirect_uri, self.api_version)

        logging.info(f"Please go to this URL and authorize the application: {response.url}")

        # Get the authorization code from the user
        auth_code = input("Enter the authorization code: ")

        # Get the access token
        api_response = self.api_instance.token(
            self.api_version,
            code=auth_code,
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            grant_type="authorization_code",
        )

        self._store_tokens(api_response)
        self._create_api_client(self.access_token)
        return self.api_client

    def _store_tokens(self, api_response):
        """Stores access and refresh tokens."""
        self.access_token = api_response.access_token
        os.environ["UPSTOX_ACCESS_TOKEN"] = self.access_token

        # Read existing .env file
        if os.path.exists(".env"):
            with open(".env", "r") as f:
                lines = f.readlines()
        else:
            lines = []

        # Write new values, updating existing ones
        with open(".env", "w") as f:
            for line in lines:
                if not line.startswith("UPSTOX_ACCESS_TOKEN") and not line.startswith("UPSTOX_REFRESH_TOKEN"):
                    f.write(line)
            f.write(f"UPSTOX_ACCESS_TOKEN='{self.access_token}'\n")
            if hasattr(api_response, 'refresh_token') and api_response.refresh_token:
                self.refresh_token = api_response.refresh_token
                os.environ["UPSTOX_REFRESH_TOKEN"] = self.refresh_token
                f.write(f"UPSTOX_REFRESH_TOKEN='{self.refresh_token}'\n")

    def refresh_access_token(self):
        """Refreshes the access token using the refresh token."""
        if not self.refresh_token:
            logging.warning("No refresh token available. Please login again.")
            return self.login()

        try:
            api_response = self.api_instance.token(
                self.api_version,
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                grant_type="refresh_token",
                refresh_token=self.refresh_token
            )

            self._store_tokens(api_response)
            self._create_api_client(self.access_token)
            logging.info("Access token refreshed successfully.")
            return self.api_client
        except upstox_client.ApiException as e:
            logging.error(f"Failed to refresh access token: {e}", exc_info=True)
            return None

    def _create_api_client(self, access_token):
        """
        Creates an API client instance with the given access token.
        """
        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        self.api_client = upstox_client.ApiClient(configuration)
        return self.api_client

    def get_api_client(self):
        """
        Returns the API client instance, trying to use existing tokens first.
        """
        if self.access_token:
            self._create_api_client(self.access_token)
        else:
            self.login()
        return self.api_client
