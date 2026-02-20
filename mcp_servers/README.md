# MCP Servers

This directory contains the implementation of several MCP servers.  
Each server exposes a focused set of tools and handles a specific function. They are designed to be modular, easy to test, and runnable either standalone or via an MCP Aggregator.

## Available Servers

- **[`mcp_agenda.py`](./mcp_agenda.py)**  
  Manage simple personal-agenda data: list events, add new ones, and delete existing items.

- **[`mcp_consumption.py`](./mcp_consumption.py)**  
  Query and analyze OCI consumption metrics by service and by compartment.

- **[`mcp_employee.py`](./mcp_employee.py)**  
  Return employee records for a fictional company, including basic metadata and vacation-day usage.

- **[`mcp_github.py`](./mcp_github.py)**  
  Read the structure and file contents of a GitHub repository using a personal access token.

- **[`mcp_internet_search.py`](./mcp_internet_search.py)**  
  Perform Internet searches and return the top relevant results.

- **[`mcp_selectai.py`](./mcp_selectai.py)**  
  Provide Text-to-SQL capabilities using Oracle Autonomous Database SelectAI.

- **[`mcp_semantic_search.py`](./mcp_semantic_search.py)**  
  Execute semantic search over Oracle Database 23c/26AI using OCI GenAI embeddings and IAM-secured access.

