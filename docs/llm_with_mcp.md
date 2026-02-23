# AgentWithMCP Backend Documentation

## Purpose

`llm_with_mcp.py` implements the backend agent used by the Streamlit UI.

Main responsibilities:
- Discover MCP tools from a remote MCP server.
- Bind discovered tools to a LangChain chat model.
- Run a tool-calling loop until the model returns a final answer.
- Expose both:
  - non-streaming API (`answer`, `run`)
  - event streaming API for tool activity (`answer_streaming`, `run_streaming`, `run_streaming_sync`)
- Optionally stream raw LLM text without tools (`stream_text_only`).

## Current Public API

Supported entry points:
- `AgentWithMCP.create(...)`
- `AgentWithMCP.answer(question, history=None)`
- `AgentWithMCP.answer_streaming(question, history=None)`
- `run(question, history)`
- `run_streaming(question, history)`
- `run_streaming_sync(question, history, on_event)`

## Important Clarification About Streaming

`answer_streaming` does not stream answer tokens.

It streams:
- lifecycle event `start`
- tool events (`tool_call`, `tool_result`, `tool_error`)
- one final event `final_answer` containing the complete answer text and metadata

If you need token-level streaming, use `stream_text_only` (no tools).

## High-Level Flow

1. Create the model via `get_llm(model_id=...)`.
2. List tools from MCP (`MCPClient.list_tools()`).
3. Convert MCP tool schemas to JSON schema format expected by LangChain.
4. Sanitize tool names to provider-safe names (`[A-Za-z0-9_-]`) and keep an alias map.
5. Convert schemas to Pydantic models and call `.bind_tools(...)`.
6. Build messages (system prompt + history + current user prompt).
7. Execute loop:
   - invoke LLM
   - if tool calls exist, execute MCP tools and append `ToolMessage`
   - continue until no tool calls remain
8. Return final answer and metadata.

## Configuration Inputs

The module reads configuration from `config.py`, `config_private.py`, and `mcp_servers_config.py`.

Important values:
- `USERNAME`
- `IAM_BASE_URL`
- `ENABLE_JWT_TOKEN`
- `DEBUG`
- `OCI_APM_TRACES_URL`
- `OTEL_SERVICE_NAME`
- `SECRET_OCID`
- `OCI_APM_DATA_KEY`
- `MCP_SERVERS_CONFIG["default"]["url"]`

Module-level constants:
- `MAX_HISTORY = 16`
- `TIMEOUT = 60`
- `SCOPE = "urn:opc:idm:__myscopes__"`
- `DEFAULT_MODEL_ID = "xai.grok-4"`
- `QUEUE_TIMEOUT = 0.1` (internal polling timeout for streaming event queue)

## Authentication

`default_jwt_supplier()` returns a fresh JWT when `ENABLE_JWT_TOKEN` is enabled.

- JWT is used for MCP calls (`list_tools` and `call_tool`).
- If JWT is disabled, MCP calls run without auth token.

## Tool Name Compatibility

Some providers validate tool names strictly. The module:
- sanitizes discovered tool names to a safe format
- keeps `safe_name -> original_name` mapping
- resolves emitted tool names back to the original MCP tool name before execution

This prevents provider-side validation errors while preserving real MCP routing.

## Agent Methods

### `create(...)`
Async factory that initializes the agent:
- creates LLM
- discovers tools
- sanitizes schema titles
- binds tools to model

### `answer(question, history=None)`
Runs the full tool loop and returns:

```python
{
  "answer": "...",
  "metadata": {
    "tool_names": [...],
    "tool_params": [...],
    "tool_results": [...]
  }
}
```

### `answer_streaming(question, history=None)`
Async generator emitting structured events during the same tool loop.

Event types:
- `start`
- `tool_call`
- `tool_result`
- `tool_error`
- `final_answer`

`final_answer` contains the complete final text and metadata.

### `stream_text_only(question)`
Optional helper for token/text streaming without tool calling.

It builds `[SystemMessage, HumanMessage]` and yields chunks from `self.llm.astream(...)`.

## Top-Level Helpers

### `run(question, history)`
Convenience async wrapper:
1. `agent = await AgentWithMCP.create()`
2. `return await agent.answer(question, history)`

### `run_streaming(question, history)`
Convenience async wrapper returning the same events as `answer_streaming`.

### `run_streaming_sync(question, history, on_event)`
Synchronous wrapper around `run_streaming(...)`, useful for sync UI code.

## Metadata Contract

Returned metadata fields:
- `tool_names`: ordered list of executed tool names
- `tool_params`: ordered list of `{tool, args}`
- `tool_results`: ordered list of `{tool, args, result}` or `{tool, args, error}`

This structure is used by UI debug panels and citation extraction.

## UI Integration Notes

- `ui_mcp_agent.py` uses non-streaming `answer(...)`.
- `ui_mcp_agent_v2.py` uses `answer_streaming(...)` to show toast notifications for tool start/end and tool errors.
- In `ui_mcp_agent_v2.py`, the final text is shown only on `final_answer`.

## Minimal Examples

Non-streaming:

```python
import asyncio
from llm_with_mcp import AgentWithMCP

async def main():
    agent = await AgentWithMCP.create(model_id="openai.gpt-5.2")
    res = await agent.answer("Show OCI usage for January 2026", history=[])
    print(res["answer"])

asyncio.run(main())
```

Event streaming (tool notifications + final answer):

```python
import asyncio
from llm_with_mcp import run_streaming

async def main():
    async for ev in run_streaming("Analyze OCI usage", history=[]):
        print(ev["type"], ev)

asyncio.run(main())
```
