"""
Config from env
"""

import os


def _bool(env, default="false"):
    return os.getenv(env, default).strip().lower() in {"1", "true", "yes", "y"}


# Security / JWT (optional)
ENABLE_JWT_TOKEN = _bool("ENABLE_JWT_TOKEN", "false")
IAM_BASE_URL = os.getenv(
    "IAM_BASE_URL", ""
)  # e.g., https://idcs-xxx.identity.oraclecloud.com
ISSUER = os.getenv("ISSUER", "")  # e.g., https://idcs-xxx.identity.oraclecloud.com/
AUDIENCE = os.getenv("AUDIENCE", "")  # e.g., your-api-audience

# Transport
TRANSPORT = os.getenv("TRANSPORT", "streamable-http")  # "stdio" or "streamable-http"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# Oracle DB (thin mode – no Instant Client required)
# Use only if/when you actually connect in your tools
ADB_USER = os.getenv("ADB_USER", "")
ADB_PASSWORD = os.getenv("ADB_PASSWORD", "")
ADB_DSN = os.getenv(
    "ADB_DSN", ""
)  # e.g., "myadb_tp.adb.eu-frankfurt-1.oraclecloud.com"
