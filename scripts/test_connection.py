import os
import logging
from dotenv import load_dotenv
import upstox_client
from upstox_client.rest import ApiException

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_upstox_connection():
    """
    Tests the connection to the Upstox API by fetching the user profile.
    """
    load_dotenv()

    api_key = os.getenv("UPSTOX_API_KEY")
    api_secret = os.getenv("UPSTOX_API_SECRET")
    access_token = os.getenv("UPSTOX_ACCESS_TOKEN")

    if not all([api_key, api_secret, access_token]):
        logging.error("API key, secret, or access token is missing. Please check your .env file.")
        return

    # Configure API client
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api_client = upstox_client.ApiClient(configuration)

    api_version = "v2"

    try:
        # Create an instance of the UserApi
        user_api_instance = upstox_client.UserApi(api_client)

        # Get user profile
        api_response = user_api_instance.get_profile(api_version)

        logging.info("Successfully connected to Upstox API.")
        logging.info(f"User Profile: {api_response.data}")

    except ApiException as e:
        logging.error(f"Exception when calling UserApi->get_profile: {e}")
        if e.status == 401:
            logging.error("Unauthorized. Your access token may be expired or invalid.")
        else:
            logging.error(f"API Error: {e.body}")

if __name__ == "__main__":
    test_upstox_connection()
