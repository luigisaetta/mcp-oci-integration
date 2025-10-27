"""
Client utility for JWT issuer

To be used with MCP-CONTEXT_FORGE from IBM MCP Gateway.
"""

import requests
from requests.auth import HTTPBasicAuth

# --- configuration ---
# JWT issuer service URL
# check your local setup
ISSUER_URL = "http://localhost:8081/token"

# Gateway username to embed
# USERNAME_CLAIM = "admin@example.com"
# the user must be defined and admin
USERNAME_CLAIM = "user01@example.com"

# token lifetime
EXP_SECONDS = 3600

TIMEOUT = 30
# --- configuration ---


def get_jwt_token(
    basic_user: str,
    basic_pass: str,
) -> str:
    """
    Obtain a JWT from the issuer service.
    """

    try:
        resp = requests.post(
            ISSUER_URL,
            auth=HTTPBasicAuth(basic_user, basic_pass),
            # we need to pass a valid username and exp_seconds
            data={"username": USERNAME_CLAIM, "exp_seconds": EXP_SECONDS},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
    except Exception as e:
        print("❌ Error obtaining JWT from issuer:", str(e))
        raise

    return token
