"""
This is an MCP Server that provides Internat Search capabilities.
"""

from typing import Dict, Any
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage

from oci_models import get_llm
from mcp_utils import run_server
from config import (
    # first four needed only to manage JWT
    ENABLE_JWT_TOKEN,
    IAM_BASE_URL,
    ISSUER,
    AUDIENCE,
)

# using OpenAI for Internet Search
MODEL_4_SEARCH = "openai.gpt-4o-search-preview"

PROMPT_TEMPLATE_SEARCH = """
You're an expert researcher.

Provide key points and summaries from credible sources about: {topic}.
"""

AUTH = None

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

mcp = FastMCP("OCI MCP Internet Search", auth=AUTH)


#
# MCP tools definition
# add and write the code for the tools here
# mark each tool with the annotation
#
@mcp.tool
def internet_search(query: str) -> Dict[str, Any]:
    """
    Return the result of Internet Search for
    the provided query.

    Args:
        query (str): the request for Internet Search.

    Returns:
        str: text + the references.

    """
    llm = get_llm(model_id=MODEL_4_SEARCH)

    prompt_search = PromptTemplate(
        input_variables=["topic"], template=PROMPT_TEMPLATE_SEARCH
    ).format(topic=query)

    result = llm.invoke([HumanMessage(content=prompt_search)]).content

    return {"search_result": result}


#
# Run the MCP server
#
if __name__ == "__main__":
    run_server(mcp)
