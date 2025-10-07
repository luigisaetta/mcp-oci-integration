"""
Text2SQL MCP server based on ADB Select AI

It requires that a Select AI profile has already been created
in the DB schema used for the DB connection.
"""

from typing import Any, Dict
from fastmcp import FastMCP

# to verify the JWT token
# if you don't need to add security, you can remove this
# uses the new verifier from latest FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier

# here is the function that calls Select AI
from consumption_utils import (
    usage_summary_by_service_structured,
    usage_summary_by_compartment_structured,
)
from mcp_utils import run_server
from utils import get_console_logger

from config import (
    DEBUG,
    # first four needed only to manage JWT
    ENABLE_JWT_TOKEN,
    IAM_BASE_URL,
    ISSUER,
    AUDIENCE,
)

AUTH = None
logger = get_console_logger()

#
# if you don't need to add security, you can remove this part and set
# AUTH = None, or simply set ENABLE_JWT_TOKEN = False
#
if ENABLE_JWT_TOKEN:
    # check that a valid JWT token is provided
    AUTH = JWTVerifier(
        # this is the url to get the public key from IAM
        # the PK is used to check the JWT
        jwks_uri=f"{IAM_BASE_URL}/admin/v1/SigningCert/jwk",
        issuer=ISSUER,
        audience=AUDIENCE,
    )

mcp = FastMCP("OCI Consumption MCP server", auth=AUTH)


#
# MCP tools definition
#
# results are wrapped
#
@mcp.tool
def usage_summary_by_service(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Return the consumption aggregated by service.

    Args:
        start_date: start date of the period. Format: YYYY-MM-DD
        end_date: end date of the period. Format: YYYY-MM-DD

    Returns:
        a structure with details of consumption.

    """
    if DEBUG:
        logger.info("Called generate_sql...")

    try:
        results = usage_summary_by_service_structured(start_date, end_date)
    except Exception as e:
        logger.error("Error generating consumption: %s", e)
        results = {"error": str(e)}

    return results


@mcp.tool
def usage_summary_by_compartment(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Return the consumption aggregated by compartment.

    Args:
        start_date: start date of the period. Format: YYYY-MM-DD
        end_date: end date of the period. Format: YYYY-MM-DD

    Returns:
        a structure with details of consumption.

    """
    if DEBUG:
        logger.info("Called generate_sql...")

    try:
        results = usage_summary_by_compartment_structured(start_date, end_date)
    except Exception as e:
        logger.error("Error generating consumption: %s", e)
        results = {"error": str(e)}

    return results


#
# Run the Select AI MCP server
#
if __name__ == "__main__":
    run_server(mcp)
