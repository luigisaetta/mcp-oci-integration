"""
Semantic Search exposed as an MCP tool
with added security with OCI IAM and JWT tokens.
This version implements OpenAI spec and can be integrated
with ChatGPT Deep Research.

To be fully compliant you need to implement two tools:
* search (returns the list of IDs)
* fetch (return the text given the ID)

Author: L. Saetta
License: MIT
"""

from typing import Annotated, Dict, Any
from pydantic import Field

from fastmcp import FastMCP

# to verify the JWT token
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_http_headers

from utils import get_console_logger
from oci_models import get_embedding_model, get_oracle_vs
from db_utils import (
    get_connection,
    list_collections,
    list_books_in_collection,
    fetch_text_by_id,
)
from config import EMBED_MODEL_TYPE
from config import DEBUG, IAM_BASE_URL, ENABLE_JWT_TOKEN, ISSUER, AUDIENCE
from config import TRANSPORT, HOST, PORT

logger = get_console_logger()

AUTH = None

if ENABLE_JWT_TOKEN:
    # check that a valid JWT token is provided
    # see docs here: https://gofastmcp.com/servers/auth/bearer
    AUTH = JWTVerifier(
        # this is the url to get the public key from IAM
        # the PK is used to check the JWT
        jwks_uri=f"{IAM_BASE_URL}/admin/v1/SigningCert/jwk",
        issuer=ISSUER,
        audience=AUDIENCE,
    )

# create the app
# cool, the OAUTH 2.1 provider is pluggable
mcp = FastMCP("Demo Deep Search as MCP server", auth=AUTH)


#
# Helper functions
#
def log_headers():
    """
    if DEBUG log the headers in the HTTP request
    """
    if DEBUG:
        headers = get_http_headers(include_all=True)
        logger.info("Headers: %s", headers)


#
# MCP tools definition
#
@mcp.tool
def get_collections() -> list:
    """
    Get the list of collections (DB tables) available in the Oracle Vector Store.
    Returns:
        list: A list of collection names.
    """
    # check that a valid JWT is provided
    if ENABLE_JWT_TOKEN:
        log_headers()

    return list_collections()


@mcp.tool
def get_books_in_collection(
    collection_name: Annotated[
        str, Field(description="The name of the collection (DB table) to search in.")
    ] = "BOOKS",
) -> list:
    """
    Get the list of books in a specific collection.
    Args:
        collection_name (str): The name of the collection (DB table) to search in.
    Returns:
        list: A list of book titles in the specified collection.
    """
    # check that a valid JWT is provided
    if ENABLE_JWT_TOKEN:
        log_headers()

    try:
        books = list_books_in_collection(collection_name)
        return books
    except Exception as e:
        logger.error("Error getting books in collection: %s", e)
        return []


@mcp.tool
def search(
    query: Annotated[
        str, Field(description="The search query to find relevant documents.")
    ],
    top_k: Annotated[int, Field(description="TOP_K parameter for search")] = 5,
    collection_name: Annotated[
        str, Field(description="The name of DB table")
    ] = "BOOKS",
) -> dict:
    """
    Perform a semantic search based on the provided query.
    Args:
        query (str): The search query.
        top_k (int): The number of top results to return.
        collection_name (str): The name of the collection (DB table) to search in.
    Returns:
        dict: a dictionary containing the relevant documents.
    """
    # here only log
    if ENABLE_JWT_TOKEN:
        log_headers()
        # no verification here, delegated to BearerAuthProvider

    try:
        # must be the same embedding model used during load in the Vector Store
        embed_model = get_embedding_model(EMBED_MODEL_TYPE)

        # get a connection to the DB and init VS
        with get_connection() as conn:
            v_store = get_oracle_vs(
                conn=conn,
                collection_name=collection_name,
                embed_model=embed_model,
            )
            relevant_docs = v_store.similarity_search(query=query, k=top_k)

            if DEBUG:
                logger.info("Result from the similarity search:")
                logger.info(relevant_docs)

    except Exception as e:
        logger.error("Error in MCP deep search: %s", e)
        error = str(e)
        return {"error": error}

    # process relevant docs to be OpenAI compliant
    results = []

    for doc in relevant_docs:
        result = {
            "id": doc.metadata["ID"],
            "title": doc.metadata["source"],
            # here we return a snippet of text
            "text": doc.page_content,
            "url": "",
        }
        results.append(result)

        if DEBUG:
            logger.info(result)

    return {"results": results}


@mcp.tool
def fetch(id: str, collection_name: str = "BOOKS") -> Dict[str, Any]:
    """
    Retrieve complete document content by ID for detailed
    analysis and citation. This tool fetches the full document
    content from OpenAI Vector Store. Use this after finding
    relevant documents with the search tool to get complete
    information for analysis and proper citation.

    Args:
        id: File ID from vector store (file-xxx) or local document ID

    Returns:
        Complete document with id, title, full text content,
        optional URL, and metadata

    Raises:
        ValueError: If the specified ID is not found
    """
    if not id:
        raise ValueError("Document ID is required")

    # execute the query on the DB
    result = fetch_text_by_id(id=id, collection_name=collection_name)
    text_value = result["text_value"]
    title = result["source"]

    # formatting result as required by OpenAI specs
    # we could add metadata
    result = {"id": id, "title": title, "text": text_value, "url": "", "metadata": None}

    return result


#
# Run the MCP server
#
if __name__ == "__main__":
    if DEBUG:
        LOG_LEVEL = "DEBUG"
    else:
        LOG_LEVEL = "INFO"

    mcp.run(
        transport=TRANSPORT,
        # Bind to all interfaces
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL,
    )
