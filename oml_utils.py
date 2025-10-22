"""
OML utils (only to integrate in AI-DP demo)
"""

import json
import requests

from config_private import OML_USERNAME, OML_PASSWORD

# settings
URL_TOKEN = "https://g5e60ebadf0d95a-reusableadw.adb.eu-frankfurt-1.oraclecloudapps.com/omlusers/api/oauth2/v1/token"
URL_PREDICT = "https://g5e60ebadf0d95a-reusableadw.adb.eu-frankfurt-1.oraclecloudapps.com/omlmod/v1/deployment/predict_driver_rank/score"


#
# Utility functions for making HTTP requests to OML endpoints
#
def post_json_request(url: str, payload: dict, headers: dict | None = None) -> dict:
    """
    Sends a POST request with JSON payload and returns the JSON response.

    Args:
        url (str): The endpoint URL.
        payload (dict): The JSON payload to send in the body.
        headers (dict, optional): Additional headers to include.

    Returns:
        dict: Parsed JSON response from the server.

    Raises:
        requests.HTTPError: If the request fails (non-2xx status code).
        ValueError: If the response is not valid JSON.
    """
    # Default headers always included
    # other can be added via headers param
    default_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if headers:
        default_headers.update(headers)

    try:
        response = requests.post(url, json=payload, headers=default_headers, timeout=10)
        response.raise_for_status()  # Raise for HTTP errors

        # Parse JSON response
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"HTTP Request failed: {e}")
        raise
    except ValueError as e:
        print(f"Invalid JSON in response: {e}")
        raise


def get_token(url: str, payload: dict, headers: dict | None = None) -> dict:
    """
    Sends a POST request to obtain a token and returns the JSON response.

    Args:
        url (str): The token endpoint URL.
        payload (dict): The JSON payload to send in the body.
        headers (dict, optional): Additional headers to include.

    Returns:
        dict: Parsed JSON response containing the token.

    Raises:
        requests.HTTPError: If the request fails (non-2xx status code).
        ValueError: If the response is not valid JSON.
    """
    return post_json_request(url, payload, headers)


def get_predictions(
    race_year: int = 2024,
    total_points: float = 250.0,
    team_budget: int = 100,
    driver_age: int = 27,
) -> dict:
    """
    Example function to get predictions from OML endpoint.

    Returns:
    """
    # first get token
    _payload = {
        "grant_type": "password",
        "username": OML_USERNAME,
        "password": OML_PASSWORD,
    }

    _response = post_json_request(URL_TOKEN, _payload, headers=None)
    token = _response.get("accessToken")

    # then use token to call another endpoint
    _headers = {"Authorization": f"Bearer {token}"}

    _payload = {
        "inputRecords": [
            {
                "RACE_YEAR": race_year,
                "TOTAL_POINTS": total_points,
                "TEAM_BUDGET": team_budget,
                "DRIVER_AGE": driver_age,
            },
        ],
        "topN": 0,
        "topNdetails": 0,
    }

    _response = post_json_request(URL_PREDICT, _payload, _headers)

    scorings = []

    for score in _response["scoringResults"]:
        score = round(score["regression"], 2)
        scorings.append(score)

    return {"predictions": scorings}


# Example usage
if __name__ == "__main__":

    predictions = get_predictions()

    # scorings is a list of prediction results
    print("Prediction Response:")
    print(json.dumps(predictions, indent=2))
