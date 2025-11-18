"""
MCP proxy using FastMCP

This is a simpler way to aggregate multiple MCP servers
under a single endpoint, using directly what is provided by FastMCP.

Start with `python mcp_proxy.py`
"""

from fastmcp import FastMCP

HOST = "0.0.0.0"
PORT = 6000
TRANSPORT = "http"

config = {
    "mcpServers": {
        "oci_consumption": {"url": "http://localhost:9500/mcp", "transport": "http"},
        "semantic_search": {"url": "http://localhost:9000/mcp", "transport": "http"},
    }
}

mcp_proxy = FastMCP.as_proxy(config, name="Composite Proxy")

if __name__ == "__main__":
    mcp_proxy.run(transport=TRANSPORT, host=HOST, port=PORT)
