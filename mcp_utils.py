"""
Shared MCP code

mcp_utils
"""

import argparse
from config import TRANSPORT, PORT, HOST


def run_server(mcp):
    """
    Run the Select AI MCP server, with optional command line overrides
    for port (defaults to config.PORT).

    mcp is the server instance created with FastMCP()
    """
    if TRANSPORT not in {"stdio", "streamable-http"}:
        raise RuntimeError(f"Unsupported TRANSPORT: {TRANSPORT}")

    # parse CLI arguments
    parser = argparse.ArgumentParser(description="Run the Select AI MCP server")
    parser.add_argument(
        "--port",
        type=int,
        default=PORT,
        help=f"Port to run the MCP server on (default: {PORT} from config.py)",
    )
    args = parser.parse_args()

    # run the MCP server
    if TRANSPORT == "stdio":
        mcp.run(transport=TRANSPORT)
    else:
        mcp.run(
            transport=TRANSPORT,
            host=HOST,
            port=args.port,
        )
