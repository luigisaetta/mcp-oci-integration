# MCP Oracle OCI integrations
This repository contains code and examples to help in the following tasks:
* **Develop** MCP servers in **Python**
* **Run** MCP servers on **Oracle OCI**
* **Integrate** MCP servers with **AI Agents**
* **Integrate** MCP servers with **OCI resources** (ADB, Select AI, ...)
* **Integrate** MCP Servers running on OCI with AI Assistants like **ChatGPT**, Claude.ai, MS Copilot

![MCP console](./images/mcp_cli.png)

## What is MCP?
**MCP (Model Context Protocol)** is an **open-source standard** that lets AI models (e.g. LLMs or agents) connect bidirectionally with external tools, data sources, and services via a unified interface. 

It replaces the “N × M” integration problem (where each AI × data source requires custom code) with one standard protocol. 

MCP supports **dynamic discovery** of available tools and context, enabling:
* AI Assistants to get access to relevant information, available in Enterprise Knowledge base.
* Agents to reason and chain actions across disparate systems. 

It’s quickly gaining traction: major players like OpenAI, Google DeepMind, Oracle are adopting it to make AI systems more composable and interoperable. 

In today’s landscape of agentic AI, MCP is critical because it allows models to act meaningfully in real-world systems rather than remaining isolated black boxes.

## Develop MCP Servers in Python
The easiest way is to use the [FastMCP](https://gofastmcp.com/getting-started/welcome) library.

**Examples**:
* in [Minimal MCP Server](./minimal_mcp_server.py) you'll find a **good, minimal example** of a server exposing two tools, with the option to protect it using JWT.

If you want to start with **something simpler**, have a look at [how to start developing MCP](./how_to_start_mcp.md). It is simpler, with no support for JWT tokens.

## How to test
If you want to quickly test the MCP server you have developed (or the minimal example provided here) you can use the [Streamlit UI](./ui_mcp_agent.py).

In the Streamlit application, you can:
* Specify the URL of the MCP server (default is in [mcp_servers_config.py](./mcp_servers_config.py))
* Select one of models available in OCI Generative AI
* test making questions answered using the tools exposed by the MCP server.

In [llm_with_mcp.py](./llm_with_mcp.py) there is the complete implementation of the tool calling loop.

## Semantic Search
In this repository there is a complete implementation of an MCP server implementing Semantic Search on top of Oracle 23AI.
You need only to oad the documents in the Oracle DB and put the right configuration, to connect to DB, in config_private.py.

It is wip... coming soon.

