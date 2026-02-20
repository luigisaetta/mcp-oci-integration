"""
MCP server config

You can put the info required to access MCP server here
"""

import os


MCP_SERVERS_CONFIG = {
    "default": {
        "transport": "streamable_http",
        "url": os.getenv("MCP_DEFAULT_URL", "http://localhost:6000/mcp"),
    },
}
