# MCP Oracle OCI integrations
This repository contains code and examples to help in the following tasks:
* Develop MCP servers in Python
* Run MCP servers on Oracle OCI
* Integrate MCP servers with AI Agents
* Integrate MCP servers with OCI resources (ADB, Select AI, ...)
* Integrate MCP Servers running on OCI with AI Assistants like ChatGPT, Claude.ai, MS Copilot

## Develop MCP Servers in Python
The easiest way is to use the [FastMCP](https://gofastmcp.com/getting-started/welcome) library.

**Examples**:
* in [Minimal MCP Server](./minimal_mcp_server.py) you'll find a **good, minimal example** of a server exposing two tools, with the option to protect it using JWT.

If you want to start with something simpler, have a look at [how to start developing MCP](./how_to_start_mcp.md). It is simpler, with no support for JWT tokens.

