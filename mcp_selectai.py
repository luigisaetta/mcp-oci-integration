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
from db_utils import generate_sql_from_prompt, execute_generated_sql
from mcp_utils import run_server
from utils import get_console_logger

from config import (
    DEBUG,
    # first four needed only to manage JWT
    ENABLE_JWT_TOKEN,
    IAM_BASE_URL,
    ISSUER,
    AUDIENCE,
    # select ai
    SELECT_AI_PROFILE,
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

mcp = FastMCP("OCI Select AI MCP server", auth=AUTH)


#
# MCP tools definition
# add and write the code for the tools here
# mark each tool with the annotation
#
# results are wrapped
#
@mcp.tool
def generate_sql(user_request: str) -> Dict[str, Any]:
    """
    Return the SQL generated for the user request.

    Args:
        user_request (str): the request to be translated in SQL.

    Returns:
        str: the SQL generated.

    Examples:
        >>> generate_sql("List top 5 customers by sales")
        SQL...
    """
    if DEBUG:
        logger.info("Called generate_sql...")

    try:
        results = generate_sql_from_prompt(SELECT_AI_PROFILE, user_request)
    except Exception as e:
        logger.error(f"Error generating SQL for request '{user_request}': {e}")
        results = {"error": str(e)}

    return results


@mcp.tool
def execute_sql(sql: str) -> Dict[str, Any]:
    """
    Execute the SQL generated
    """
    if DEBUG:
        logger.info("Called execute_sql...")
    try:
        results = execute_generated_sql(sql)
    except Exception as e:
        logger.error(f"Error executing SQL '{sql}': {e}")
        results = {"error": str(e)}

    return results


#
# Run the Select AI MCP server
#
if __name__ == "__main__":
    run_server(mcp)
