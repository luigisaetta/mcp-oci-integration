# AgentWithMCP Backend – Documentation

## 1. Purpose

This module implements the **backend agent** used by the Streamlit MCP UI.  
Its main responsibilities are:

- Orchestrate an **LLM (LangChain chat model)** with tools exposed by an **MCP server**.
- Secure all MCP calls using **JWT tokens** issued by **OCI IAM** (optional).
- Add **OCI APM tracing** around LLM and tool calls.
- Provide both:
  - A **non-streaming** API that returns a final answer + metadata.
  - A **streaming** API that emits structured events (tool calls/results/errors + final answer).

The result is a reusable Python agent that can be used by any UI or service, not only Streamlit.

---

## 2. Software Architecture

### 2.1 High-Level Components

- **MCP Server (external)**  
  Exposes tools over a URL (`MCP_URL`). Tools are discovered and invoked using `fastmcp.MCPClient`.

- **LLM (LangChain Chat Model)**  
  Provided by `oci_models.get_llm(model_id=...)`. It must support:
  - `.bind_tools(pydantic_models)`: to attach tools.
  - `.ainvoke(messages)`: to run the model with tool support.
  - `.astream(messages)`: for raw text streaming (no tools).

- **Security Layer (JWT / OCI IAM)**  
  - `OCIJWTClient` obtains a short-lived JWT from OCI IAM using:
    - `IAM_BASE_URL`
    - `SCOPE`
    - `SECRET_OCID`
  - JWT is attached to MCP calls when `ENABLE_JWT_TOKEN` is `True`.

- **Tracing Layer (OCI APM / OpenTelemetry)**  
  - `setup_tracing(...)` configures OTEL with:
    - `OTEL_SERVICE_NAME`
    - `OCI_APM_TRACES_URL`
    - `OCI_APM_DATA_KEY`
  - `start_span(...)` wraps LLM and MCP tool calls.

- **AgentWithMCP**  
  - Central orchestrator:
    - Discovers tools from MCP.
    - Binds schemas → Pydantic models → tools to the LLM.
    - Runs the tool-calling loop until a final answer is produced.
    - Supports **non-streaming** and **streaming** APIs.

- **Top-Level Helpers**  
  - `run(question, history)` – simple non-streaming entry point.
  - `run_streaming(question, history)` – async streaming entry point.
  - `run_streaming_sync(question, history, on_event)` – sync wrapper for streaming (for UIs).

---

## 3. Configuration

The module reads configuration from `config`, `config_private`, and `mcp_servers_config`:

- From `config`:
  - `USERNAME` – user name injected into the system prompt.
  - `IAM_BASE_URL` – IAM endpoint used by `OCIJWTClient`.
  - `ENABLE_JWT_TOKEN` – if `True`, all MCP calls are authenticated using JWT.
  - `DEBUG` – enables verbose logging (including `oci` SDK logger).
  - `OCI_APM_TRACES_URL` – endpoint for OCI APM traces.
  - `OTEL_SERVICE_NAME` – service name used in OTEL tracing.

- From `config_private`:
  - `SECRET_OCID` – OCID of the secret containing the credentials for JWT.
  - `OCI_APM_DATA_KEY` – APM data key for authentication.

- From `mcp_servers_config`:
  - `MCP_SERVERS_CONFIG["default"]["url"]` → `MCP_URL` (MCP server endpoint).

- Module-level constants:
  - `MAX_HISTORY = 16` – maximum number of history messages to keep.
  - `MCP_URL` – default MCP endpoint.
  - `TIMEOUT = 60` – MCP client timeout (seconds).
  - `SCOPE = "urn:opc:idm:__myscopes__"` – OAuth scope for JWT.
  - `DEFAULT_MODEL_ID = "xai.grok-4"` – default LLM model ID.
  - `QUEUE_TIMEOUT = 0.1` – timeout for reading streaming events from the internal queue.

- System prompt:
  - `SYSTEM_PROMPT_TEMPLATE = AGENT_SYSTEM_PROMPT_TEMPLATE`  
    The template is formatted with:
    - `username`
    - `today_long`
    - `today_iso`

---

## 4. Functions and Classes – High-Level Overview

### 4.1 `default_jwt_supplier() -> Optional[str]`

**Purpose:**  
Central place to obtain a **fresh JWT token** for MCP calls.

**Behavior:**

- If `ENABLE_JWT_TOKEN` is `True`:
  - Uses `OCIJWTClient(IAM_BASE_URL, SCOPE, SECRET_OCID).get_token()`
  - Returns the token string (without `"Bearer "` prefix).
- If `ENABLE_JWT_TOKEN` is `False`:
  - Returns `None` (no auth on MCP calls).

Used by `AgentWithMCP` to transparently handle authentication.

---

### 4.2 `schemas_to_pydantic_models(schemas: List[Dict[str, Any]]) -> List[type[BaseModel]]`

**Purpose:**  
Convert a list of **JSON Schema** dicts (as used by MCP tools) into **Pydantic models** compatible with LangChain’s `.bind_tools(...)`.

**Key points:**

- Accepts top-level JSON Object schemas (`type: "object"`).
- Maps JSON types `"string"`, `"integer"`, `"number"`, `"boolean"` to Python types.
- Uses field `title`/`description` for parameter documentation.
- Required properties are modeled as non-optional (`...`).
- Returns a list of dynamically created `BaseModel` subclasses.

This is especially important for compatibility with **non-Cohere** models that can be picky about tool schemas.

---

### 4.3 `build_system_prompt() -> str`

**Purpose:**  
Create a **dynamic system prompt** using the template and current date/time.

**Behavior:**

- Gets current time in `Europe/Rome` (`ZoneInfo`).
- Computes:
  - `today_iso = "YYYY-MM-DD"`
  - `today_long = "Weekday, DD Month YYYY, HH:MM:SS TZ"`
- Formats `SYSTEM_PROMPT_TEMPLATE` with:
  - `username = USERNAME`
  - `today_long`
  - `today_iso`

Used by `AgentWithMCP` to prepend context to every conversation.

---

### 4.4 `class AgentWithMCP`

**Purpose:**  
The core **LLM + MCP orchestrator**.

It:

- Discovers tools from the MCP server.
- Converts tool schemas → Pydantic models → binds them to the LLM.
- Manages the tool-calling loop for:
  - Non-streaming (`answer`).
  - Streaming (`answer_streaming`).
- Integrates **OCI APM tracing** around all LLM and tool operations.

#### `__init__(self, mcp_url, jwt_supplier, timeout, llm)`

- Stores configuration and collaborators:
  - `mcp_url`, `jwt_supplier`, `timeout`, `llm`.
- Initializes:
  - `self.model_with_tools = None`
- Calls `setup_tracing(...)` to configure OTEL/OCI APM.

**Note:** `__init__` is non-async; actual initialization is done in `create()`.

---

#### `@staticmethod _tool_to_schema(t: object) -> dict`

**Purpose:**  
Normalize an MCP tool object into a JSON Schema dict.

- Reads:
  - `t.name`
  - `t.description`
  - `t.inputSchema`
- Ensures the schema is an `object` with `properties`.
- This schema is later passed to `schemas_to_pydantic_models`.

---

#### `async _list_tools(self)`

**Purpose:**  
Fetch the list of tools exposed by the MCP server.

**Behavior:**

- Gets JWT (if enabled).
- Opens an async `MCPClient` session with `self.mcp_url`.
- Calls `c.list_tools()`.
- Returns a list of tool objects.

Used by `create()` during agent initialization.

---

#### `async _call_tool(self, name: str, args: Dict[str, Any])`

**Purpose:**  
Execute a **single MCP tool call**.

- Gets JWT (if enabled).
- Opens `MCPClient(self.mcp_url, auth=jwt, timeout=self.timeout)`.
- Calls `c.call_tool(name, args or {})`.
- Returns the raw result (MCP response object).

Used by `_run_tool_loop()` for each tool call emitted by the LLM.

---

#### `@classmethod async create(cls, mcp_url=MCP_URL, jwt_supplier=default_jwt_supplier, timeout=TIMEOUT, model_id=DEFAULT_MODEL_ID)`

**Purpose:**  
Async factory that returns a **fully initialized AgentWithMCP**.

**Steps:**

1. Gets an LLM via `get_llm(model_id)`.
2. Instantiates `AgentWithMCP(mcp_url, jwt_supplier, timeout, llm)`.
3. Fetches tools via `_list_tools()`.
4. Builds schemas via `_tool_to_schema(...)`.
5. Converts schemas → Pydantic models via `schemas_to_pydantic_models()`.
6. Binds tools to the LLM:
   - `self.model_with_tools = self.llm.bind_tools(pyd_models)`.

Returns the ready-to-use `AgentWithMCP` instance.

---

#### `_build_messages(...) -> List[Any]`

**Purpose:**  
Build the list of **LangChain messages** used for each request.

**Inputs:**

- `history`: list of dicts `{ "role": "user"|"assistant", "content": "<text>" }`.
- `system_prompt`: generated by `build_system_prompt()`.
- `current_user_prompt`: the new question.
- `max_history`: limit on history items (defaults to `MAX_HISTORY`).
- `exclude_last`: if `True`, drops the last history item (to avoid duplicating the current prompt).

**Output:**

- `[SystemMessage, <filtered history>, HumanMessage(current_user_prompt)]`.

---

#### `async _invoke_llm(self, messages: List[Any]) -> AIMessage`

**Purpose:**  
Single point where the LLM is called with tool support.

**Behavior:**

- Wraps the call in `start_span("llm_invoke", model=self.llm.model_id)` for APM.
- Logs `"Invoking LLM..."`.
- Calls `self.model_with_tools.ainvoke(messages)`.
- Returns the resulting `AIMessage`.

---

#### `async _run_tool_loop(self, messages, event_handler=None) -> tuple[AIMessage, Dict[str, Any]]`

**Purpose:**  
Core **LLM + MCP tool-calling loop**.

**Logic:**

1. In a `tool_calling_loop` span:
   - Invoke the LLM via `_invoke_llm`.
   - Inspect `ai.tool_calls`.
2. If no `tool_calls`:
   - Return final `AIMessage` and metadata:
     - `tool_names`, `tool_params`, `tool_results`.
3. If tool calls exist:
   - Append the AI message to `messages`.
   - For each tool call:
     - If `event_handler` is provided, emit a `"tool_call"` event.
     - Call `_call_tool(name, args)` in `tool_call` span.
     - Extract payload (`result.data` / `result.content` / `str(result)`).
     - Build a `ToolMessage` and append to `messages`.
     - Update metadata arrays.
     - Emit `"tool_result"` event (if handler is provided).
   - On exception:
     - Append an error `ToolMessage`.
     - Update `tool_results` with `error`.
     - Emit `"tool_error"` event.

**Return value:**

- Final `AIMessage` produced by the model (no more tool calls).
- `metadata` dict with full tool usage information.

---

#### `async answer(self, question: str, history: Optional[list] = None) -> dict`

**Purpose:**  
Full **non-streaming** interaction.

**Steps:**

1. Normalize `history` (default to `[]`).
2. Build `messages` via `_build_messages(...)`.
3. Run `_run_tool_loop(messages)`.
4. Return:

   ```python
   {
       "answer":   ai.content,  # final LLM answer as string
       "metadata": {
           "tool_names":   [...],
           "tool_params":  [...],
           "tool_results": [...],
       },
   }

No streaming; the caller receives the full answer only at the end.

#### `async answer_streaming(self, question: str, history: Optional[list] = None)`

**Purpose:**  
Full **streaming** interaction via an async generator of `StreamEvent` objects.

**Event flow:**

1. `{"type": "start", "question": <str>}`
2. During tool loop:
   - `{"type": "tool_call", "tool": <name>, "args": <dict>}`
   - `{"type": "tool_result", "tool": <name>, "args": <dict>, "payload": <any>}`
   - `{"type": "tool_error", "tool": <name>, "args": <dict>, "payload": <str>}`
3. At the end:
   - `{"type": "final_answer", "answer": <str>, "metadata": <dict>}`

**Implementation details:**

- Emits an immediate `"start"` event with the user question.
- Builds the same messages used by `answer()`.
- Creates an internal `asyncio.Queue` to collect events from `_run_tool_loop` via an `event_handler`.
- Spawns an async task (`_run_loop_task`) that calls `_run_tool_loop(messages, event_handler=handler)`.
- While the loop is running, it:
  - Reads events from the queue with a timeout (`QUEUE_TIMEOUT`).
  - Yields each event as soon as it becomes available.
- Once the loop finishes:
  - Ensures the task is done.
  - Raises any error that occurred inside the loop.
  - Emits a single `"final_answer"` event containing:
    - `answer`: final LLM answer string.
    - `metadata`: tool usage metadata.

---

#### `async _stream_llm_messages(self, messages: List[Any])`

**Purpose:**  
Internal helper to **stream raw text** from the underlying LLM using `.astream(...)`, **without tools**.

**Behavior:**

- Calls `self.llm.astream(messages)` and iterates over chunks.
- Normalizes different provider-specific chunk formats into plain text:
  - If `chunk.content` is a string → uses it directly.
  - If `chunk.content` is a list → extracts `.text` or `{"text": ...}` from each part and concatenates.
  - Otherwise → tries `chunk.delta` as a fallback.
- Skips empty pieces.
- Yields text fragments as they are produced.

---

#### `async stream_text_only(self, question: str)`

**Purpose:**  
Experimental helper to **stream only a plain LLM answer** (no MCP tools, no tool loop).

**Steps:**

1. Builds:
   - `SystemMessage(content=build_system_prompt())`
   - `HumanMessage(content=question)`
2. Calls `_stream_llm_messages(messages)`.
3. Yields text chunks as they arrive.

Useful for lightweight text-only streaming scenarios.

---

### 4.5 Top-Level Functions

#### `async run(question: str, history)`

**Purpose:**  
Simple non-streaming entry point.

**Behavior:**

1. Creates an `AgentWithMCP` via `AgentWithMCP.create()`.
2. Calls `agent.answer(question, history)`.
3. Returns the same dict as `answer()`:

   ```python
   {
       "answer": "<final text>",
       "metadata": {...}
   }
   
#### `async run_streaming(question: str, history)`

**Purpose:**  
Async streaming entry point. This function creates an initialized `AgentWithMCP` and yields every `StreamEvent` emitted by `answer_streaming`.

**Behavior:**
1. Creates the agent with `AgentWithMCP.create()`.
2. Delegates execution to `agent.answer_streaming(question, history)`.
3. Forwards each yielded `StreamEvent`:
   - `{"type": "start", "question": "..."}`
   - `{"type": "tool_call", "tool": "...", "args": {...}}`
   - `{"type": "tool_result", "tool": "...", "args": {...}, "payload": ...}`
   - `{"type": "tool_error", "tool": "...", "args": {...}, "payload": "..."}`
   - `{"type": "final_answer", "answer": "...", "metadata": {...}}`

**Example:**
```python
async for event in run_streaming("hello", history=[]):
    print(event)
```

---

#### `run_streaming_sync(question: str, history, on_event)`

**Purpose:**  
Synchronous wrapper around the async streaming API.  
Intended for Streamlit, CLI tools, or any environment that cannot run `async for`.

**Behavior:**
1. Defines an async driver:
   ```python
   async def _driver():
       async for ev in run_streaming(question, history):
           on_event(ev)
   ```
2. Executes it using `asyncio.run()`.
3. Calls `on_event(ev)` for each streamed event.

**Example:**
```python
def handle_event(ev):
    print("EVENT:", ev)

run_streaming_sync(
    question="Fetch latest MCP data",
    history=[],
    on_event=handle_event,
)
```

---

### Example Usage (Async)

```python
async for ev in run_streaming("Analyze my OCI costs", history=[]):
    if ev["type"] == "tool_call":
        print("Calling:", ev["tool"])
    elif ev["type"] == "tool_result":
        print("Result:", ev["payload"])
    elif ev["type"] == "final_answer":
        print("FINAL:", ev["answer"])
```

---

### Example Usage (Sync)

```python
def handle(ev):
    print(ev)

run_streaming_sync(
    question="Show last FinOps summary",
    history=[],
    on_event=handle,
)
```

---

### Plain Text Streaming (No Tools)

```python
agent = await AgentWithMCP.create()
async for chunk in agent.stream_text_only("Explain MCP"):
    print(chunk, end="")
```

---

### Summary

- `run_streaming` → async generator of `StreamEvent`
- `run_streaming_sync` → sync wrapper for UIs
- Events include:
  - `start`
  - `tool_call`
  - `tool_result`
  - `tool_error`
  - `final_answer`
- Supports real-time tool activity display in any interface.

---

### Final Summary of the Module

This module implements an orchestration layer that connects a Large Language Model with an MCP (Model Context Protocol) server. 
Its purpose is to allow the LLM to dynamically discover tools exposed by the MCP server, invoke them securely, 
and integrate their outputs into the final model response.

The architecture combines several components: an MCP client for tool discovery and execution, an LLM interface capable of tool calling, 
a security layer based on OCI IAM JWT tokens, and an optional OCI APM tracing layer that records LLM calls and tool interactions. 
The system prompt is generated dynamically, and conversation history is trimmed and processed before each request.

The heart of the module is the AgentWithMCP class, which manages tool binding, message construction, the iterative loop of model invocation and tool execution, 
and the aggregation of metadata for each tool call. It supports both standard (non-streaming) operation and a streaming mode that emits structured events as they occur. 
Additional helpers provide raw text streaming, convenience wrappers, and synchronous interfaces for environments that do not use async code.

Overall, the module provides a complete backend agent capable of secure, observable, and tool-augmented LLM execution, 
suitable for integration into Streamlit UIs or other client applications.