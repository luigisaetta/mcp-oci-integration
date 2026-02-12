"""
File name: llm_with_mcp.py
Author: Luigi Saetta
Date last modified: 2025-12-12
Python Version: 3.11

Description:
    Provides an agent for integrating LLMs with MCP servers, supporting tool calling, JWT security, APM tracing, and streaming.
    Serves as the backend for the Streamlit MCP UI.

Usage:
    Import this module and call its functions, e.g.:
        from llm_with_mcp import run, run_streaming

License:
    MIT License

Notes:
    Part of the MCP‑OCI integration demo.

Warnings:
    This module is in development and may change.

Updates:

    15/09: the code is a bit long to handle some exceptions regarding tool calling
    with all the non-cohere models through Langchain.
    As for now, it is working fine with: GPT and grok,
    some problems with llama 3.3

    27/10/2024: added APM tracing support
    01/12/2025: changed the agent to return a dict with answer and metadata

    01/12/2025: started working on Streaming support (not yet ready)
    02/12/2025: first working version with streaming events
"""

import json
import asyncio
import logging
from typing import List, Dict, Any, Callable, Sequence, Optional, TypedDict, Literal
from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import Client as MCPClient
from pydantic import BaseModel, Field, create_model
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

# our code imports
from oci_jwt_client import OCIJWTClient
from oci_models import get_llm
from agent_system_prompt import AGENT_SYSTEM_PROMPT_TEMPLATE
from utils import get_console_logger

# to integrate with OCI APM tracing
from tracing_utils import setup_tracing, start_span

from config import (
    USE_LANGCHAIN_OPENAI,
    USERNAME,
    IAM_BASE_URL,
    ENABLE_JWT_TOKEN,
    DEBUG,
    OCI_APM_TRACES_URL,
    OTEL_SERVICE_NAME,
)
from config_private import SECRET_OCID, OCI_APM_DATA_KEY
from mcp_servers_config import MCP_SERVERS_CONFIG

# for debugging
if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("oci").setLevel(logging.DEBUG)

logger = get_console_logger()

# ---- Config ----
# trim the history to max MAX_HISTORY msgs
MAX_HISTORY = 16

MCP_URL = MCP_SERVERS_CONFIG["default"]["url"]
TIMEOUT = 60
# the scope for the JWT token
SCOPE = "urn:opc:idm:__myscopes__"

DEFAULT_MODEL_ID = "xai.grok-4"

QUEUE_TIMEOUT = 0.1
# ---- Config ----

# eventually you can taylor the SYSTEM prompt here
# to help identify the tools and their usage.
# modified to be compliant to OpenAI spec.

# Use this as a template. It will be formatted with today_long/today_iso.
SYSTEM_PROMPT_TEMPLATE = AGENT_SYSTEM_PROMPT_TEMPLATE


class StreamEvent(TypedDict, total=False):
    """
    Event emitted during streaming answer.
    """

    type: Literal[
        "start",
        "tool_call",
        "tool_result",
        "tool_error",
        "final_answer",
    ]

    question: str
    tool: str
    args: Dict[str, Any]
    payload: Any
    answer: str
    metadata: Dict[str, Any]


def default_jwt_supplier() -> Optional[str]:
    """
    Get a valid JWT token to make the call to MCP server
    """
    if ENABLE_JWT_TOKEN:
        # Always return a FRESH token; do not include "Bearer " (FastMCP adds it)
        token, _, _ = OCIJWTClient(IAM_BASE_URL, SCOPE, SECRET_OCID).get_token()
    else:
        # JWT security disabled
        token = None
    return token


# mappings for schema to pyd
_JSON_TO_PY = {"string": str, "integer": int, "number": float, "boolean": bool}


# patch for OpenAI, xAI
def schemas_to_pydantic_models(schemas: List[Dict[str, Any]]) -> List[type[BaseModel]]:
    """
    transform the dict with schemas in a Pydantic object to
    solve the problems we have with non-cohere models
    """
    out = []
    for s in schemas:
        name = s.get("title", "tool")
        desc = s.get("description", "") or ""
        props = s.get("properties", {}) or {}
        required = set(s.get("required", []) or {})
        fields = {}
        for pname, spec in props.items():
            spec = spec or {}
            jtype = spec.get("type", "string")
            py = _JSON_TO_PY.get(jtype, Any)
            default = ... if pname in required else None
            # prefer property title, then description for the arg docstring
            arg_desc = spec.get("title") or spec.get("description", "")
            fields[pname] = (py, Field(default, description=arg_desc))
        model = create_model(name, __base__=BaseModel, **fields)
        model.__doc__ = desc
        out.append(model)
    return out


def build_system_prompt() -> str:
    """
    Dynamically build the system prompt with current date/time.
    """
    now = datetime.now(ZoneInfo("Europe/Rome"))
    today_iso = now.strftime("%Y-%m-%d")
    today_long = now.strftime("%A, %d %B %Y, %H:%M:%S %Z")
    return SYSTEM_PROMPT_TEMPLATE.format(
        username=USERNAME, today_long=today_long, today_iso=today_iso
    )


class AgentWithMCP:
    """
    LLM + MCP orchestrator.
    - Discovers tools from an MCP server (JWT-protected)
    - Binds tool JSON Schemas to the LLM
    - Executes tool calls emitted by the LLM and loops until completion

    This is a rather simple agent, it does only tool calling,
    but tools are provided by the MCP server.
    The code introspects the MCP server and LLM decides which tool to call
    and what parameters to provide.

    27/10: added integration with OCI APM tracing
    """

    def __init__(
        self,
        mcp_url: str,
        jwt_supplier: Callable[[], Optional[str]],
        timeout: int,
        llm,
    ):
        self.mcp_url = mcp_url
        self.jwt_supplier = jwt_supplier
        self.timeout = timeout
        self.llm = llm
        self.model_with_tools = None

        self.logger = logger

        # added to integrate with APM tracing
        setup_tracing(
            service_name=OTEL_SERVICE_NAME,
            apm_traces_url=OCI_APM_TRACES_URL,
            data_key=OCI_APM_DATA_KEY,
            propagator="tracecontext",
        )

    # ---------- helpers now INSIDE the class ----------

    @staticmethod
    def _tool_to_schema(t: object) -> dict:
        """
        Convert an MCP tool (name, description, inputSchema) to a JSON-Schema dict
        that LangChain's ChatCohere.bind_tools accepts (top-level schema).
        """
        input_schema = (getattr(t, "inputSchema", None) or {}).copy()
        if input_schema.get("type") != "object":
            input_schema.setdefault("type", "object")
            input_schema.setdefault("properties", {})
        return {
            "title": getattr(t, "name", "tool"),
            "description": getattr(t, "description", "") or "",
            **input_schema,
        }

    async def _list_tools(self):
        """
        Fetch tools from the MCP server using FastMCP. Must be async.
        """
        jwt = self.jwt_supplier()

        logger.info("Listing tools from %s ...", self.mcp_url)

        # FastMCP requires async context + await for client ops.
        async with MCPClient(self.mcp_url, auth=jwt, timeout=self.timeout) as c:
            # returns Tool objects
            return await c.list_tools()

    async def _call_tool(self, name: str, args: Dict[str, Any]):
        """
        Execute a single MCP tool call.
        """
        jwt = self.jwt_supplier()

        logger.info("Calling MCP tool '%s' with args %s", name, args)

        async with MCPClient(self.mcp_url, auth=jwt, timeout=self.timeout) as c:
            return await c.call_tool(name, args or {})

    @classmethod
    async def create(
        cls,
        mcp_url: str = MCP_URL,
        jwt_supplier: Callable[[], Optional[str]] = default_jwt_supplier,
        timeout: int = TIMEOUT,
        model_id: str = DEFAULT_MODEL_ID,
    ):
        """
        Async factory: fetch tools, bind them to the LLM, return a ready-to-use agent.
        Important: Avoids doing awaits in __init__.
        """
        # should return a LangChain Chat model supporting .bind_tools(...)
        llm = get_llm(model_id=model_id)
        # after, we call init()
        self = cls(mcp_url, jwt_supplier, timeout, llm)
        self.model_id = model_id

        tools = await self._list_tools()
        if not tools:
            logger.warning("No tools discovered at %s", mcp_url)
            tools = []

        schemas = [self._tool_to_schema(t) for t in tools]

        # wrapped with schemas_to_pyd to solve compatibility issues with non-cohere models
        pyd_models = schemas_to_pydantic_models(schemas)

        self.model_with_tools = self.llm.bind_tools(pyd_models)

        return self

    def _build_messages(
        self,
        history: Sequence[Dict[str, Any]],
        system_prompt: str,
        current_user_prompt: str,
        *,
        max_history: Optional[
            int
        ] = MAX_HISTORY,  # keep only the last N items; None = keep all
        exclude_last: bool = True,  # drop the very last history entry before building
    ) -> List[Any]:
        """
        Create: [SystemMessage(system_prompt), <trimmed history except last>,
        HumanMessage(current_user_prompt)]
        History items are dicts like {"role": "user"|"assistant", "content": "..."}
        in chronological order.
        """
        if history is None:
            history = []

        # 1) Trim to the last `max_history` entries (if set)
        if max_history is not None and max_history > 0:
            working = list(history[-max_history:])
        else:
            working = list(history)

        # 2) Optionally remove the final entry from trimmed history
        if exclude_last and working:
            working = working[:-1]

        # 3) Build LangChain messages
        msgs: List[Any] = [SystemMessage(content=system_prompt)]
        for m in working:
            role = (m.get("role") or "").lower()
            content: Optional[str] = m.get("content")
            if not content:
                continue
            if role == "user":
                msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                msgs.append(AIMessage(content=content))
            # ignore other/unknown roles (e.g., 'system', 'tool') in this simple variant

        # 4) Add the current user prompt
        msgs.append(HumanMessage(content=current_user_prompt))
        return msgs

    async def _invoke_llm(self, messages: List[Any]) -> AIMessage:
        """
        Helper.
        Single place where we call the LLM with tools.
        Also, integrate with APM (if enabled)
        Keeps tracing + logging together so we can easily change behavior later.
        """
        with start_span("llm_invoke", model=self.model_id):
            self.logger.info("Invoking LLM...")

            return await self.model_with_tools.ainvoke(messages)

    #
    # ---------- main loop ----------
    #
    async def _run_tool_loop(
        self,
        messages: List[Any],
        event_handler: Optional[Callable[[StreamEvent], None]] = None,
    ) -> tuple[AIMessage, Dict[str, Any]]:
        """
        Core LLM + MCP tool-calling loop.

        This method executes the iterative interaction between the LLM and the MCP server.
        It receives an initial list of messages (system prompt, optional history, and the
        current user prompt) and repeatedly:

        1. Invokes the LLM with the current messages.
        2. Checks whether the LLM emitted any tool calls.
        3. If no tool calls are present:
            → The loop terminates and the final AIMessage is returned.
        4. If tool calls are present:
            → Each tool call is executed against the MCP server.
            → For every tool invocation, a corresponding ToolMessage is appended
                to the message list before the next LLM invocation.

        The method returns:
            - The final AIMessage produced by the LLM (the answer after all tools are resolved).
            - A metadata dictionary containing:
                * tool_names:   list of tools invoked in order
                * tool_params:  list of parameter sets used for each tool
                * tool_results: list of raw results (or errors) returned by the tools

        If an `event_handler` callable is provided, the loop emits structured events
        as dictionaries, such as:
            - {"type": "tool_call",   "tool": <name>, "args": <dict>}
            - {"type": "tool_result", "tool": <name>, "args": <dict>, "payload": <any>}
            - {"type": "tool_error",  "tool": <name>, "args": <dict>, "payload": <str>}

        These events enable streaming of tool activity without exposing internal state.
        """

        tool_names: list[str] = []
        tool_params: list[dict] = []
        tool_results: list[dict] = []

        with start_span("tool_calling_loop", model=self.model_id):
            while True:
                ai: AIMessage = await self._invoke_llm(messages)

                tool_calls = getattr(ai, "tool_calls", None) or []
                if not tool_calls:
                    # Final answer !!!
                    metadata = {
                        "tool_names": tool_names,
                        "tool_params": tool_params,
                        "tool_results": tool_results,
                    }
                    return ai, metadata

                # --- NEW: normalize tool_call ids for providers that omit them (e.g. Gemini 2.5) ---
                for idx, tc in enumerate(tool_calls):
                    call_id = tc.get("id") or tc.get("tool_call_id")
                    if not call_id:
                        # Synthesize a stable id for this interaction
                        call_id = f"tc-{len(tool_names) + idx}"
                    # Ensure the dict has a proper 'id' field for OCI / OpenAI-style APIs
                    tc["id"] = call_id
                # --- END NEW ---

                # keep the AI msg that requested tools
                messages.append(ai)

                # Execute tool calls and append ToolMessage for each
                for tc in tool_calls:
                    name = tc["name"]
                    args = tc.get("args") or {}

                    # Defensive: ensure we always have a non-empty string id
                    # to avoid troubles with Gemini 2.5
                    call_id = tc.get("id") or tc.get("tool_call_id")
                    if not call_id:
                        call_id = f"tc-{len(tool_names)}"

                    # Notify about the tool_call if a handler is provided
                    if event_handler is not None:
                        event_handler(
                            {
                                "type": "tool_call",
                                "tool": name,
                                "args": args,
                            }
                        )

                    try:
                        # here we call the tool
                        with start_span("tool_call", tool=name):
                            result = await self._call_tool(name, args)

                            payload = (
                                getattr(result, "data", None)
                                or getattr(result, "content", None)
                                or str(result)
                            )
                            # to avoid double encoding
                            tool_content = (
                                json.dumps(payload, ensure_ascii=False)
                                if isinstance(payload, (dict, list))
                                else str(payload)
                            )
                            tm = ToolMessage(
                                content=tool_content,
                                # changed for Gemini compatibility
                                tool_call_id=call_id,
                                name=name,
                            )
                            messages.append(tm)
                            tool_names.append(name)
                            tool_params.append({"tool": name, "args": args})
                            tool_results.append(
                                {
                                    "tool": name,
                                    "args": args,
                                    "result": payload,
                                }
                            )

                            # Notify about the tool_result
                            if event_handler is not None:
                                event_handler(
                                    {
                                        "type": "tool_result",
                                        "tool": name,
                                        "args": args,
                                        "payload": payload,
                                    }
                                )

                    except Exception as e:
                        error_payload = {"error": str(e)}

                        messages.append(
                            ToolMessage(
                                content=json.dumps(error_payload),
                                tool_call_id=call_id,
                                name=name,
                            )
                        )

                        tool_results.append(
                            {
                                "tool": name,
                                "args": args,
                                "error": str(e),
                            }
                        )

                        # Notify about the tool_error
                        if event_handler is not None:
                            event_handler(
                                {
                                    "type": "tool_error",
                                    "tool": name,
                                    "args": args,
                                    "payload": str(e),
                                }
                            )

    async def answer(self, question: str, history: Optional[list] = None) -> dict:
        """
        Execute the full LLM + MCP interaction loop in non-streaming mode.

        This method builds the complete message list for the request
        (system prompt + optionally trimmed conversation history + new user message),
        then delegates execution to `_run_tool_loop`, which:

            - Invokes the LLM
            - Resolves any tool calls by querying the MCP server
            - Repeats until the model produces a final, tool-free answer

        The method returns a dictionary with the standard non-streaming response format:

        {
            "answer":   <final LLM answer as a string>,
            "metadata": {
                "tool_names":   [...],    # tools invoked in order
                "tool_params":  [...],    # arguments for each invocation
                "tool_results": [...]     # raw results or errors from each tool
            }
        }

        This is the synchronous, batched version of the agent:
        no streaming events are emitted, and the entire response becomes
        available only after the tool-calling loop completes.
        """

        # Ensure history is always a list
        if history is None:
            history = []

        # Build initial messages (system + trimmed history + current user prompt)
        messages = self._build_messages(
            history=history,
            system_prompt=build_system_prompt(),
            current_user_prompt=question,
        )

        # Delegate the core loop to the helper
        ai, metadata = await self._run_tool_loop(messages)

        # Keep the same public return format as before
        return {"answer": ai.content, "metadata": metadata}

    async def answer_streaming(self, question: str, history: Optional[list] = None):
        """
        Execute the full LLM + MCP interaction loop in streaming mode.

        This method behaves like `answer`, but instead of returning a single
        final result, it yields structured events throughout the execution
        via an async generator.

        Event sequence:

        1. `start`
            Emitted immediately, containing the user question:
                {"type": "start", "question": <str>}

        2. During the MCP tool-calling loop:
            - `tool_call`
                {"type": "tool_call", "tool": <name>, "args": <dict>}
            - `tool_result`
                {"type": "tool_result", "tool": <name>, "args": <dict>, "payload": <any>}
            - `tool_error`
                {"type": "tool_error", "tool": <name>, "args": <dict>, "payload": <str>}

            These events are emitted in real time as the LLM requests tools and the MCP
            server executes them.

        3. Final event:
            - `final_answer`
                {"type": "final_answer", "answer": <str>, "metadata": <dict>}

        Notes:
        - Only tool-related events are streamed in real time.
        - The final answer is produced only after `_run_tool_loop` has fully completed.
        - The complete answer is sent in a single `final_answer` event.
        - This interface is designed to be consumed by UI frameworks (e.g., Streamlit)
          or any synchronous code through `run_streaming_sync`.
        """

        # 1) Immediate start event
        start_event: StreamEvent = {
            "type": "start",
            "question": question,
        }
        logger.info("STREAMING EVENT (start): %s", start_event)
        yield start_event

        if history is None:
            history = []

        # 2) Build initial messages (same as in answer())
        messages = self._build_messages(
            history=history,
            system_prompt=build_system_prompt(),
            current_user_prompt=question,
        )

        # 3) Queue for events emitted by the tool loop
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        loop_done = asyncio.Event()
        final_ai: Optional[AIMessage] = None
        final_metadata: Dict[str, Any] = {}
        loop_error: Optional[Exception] = None

        # 4) event_handler used by _run_tool_loop
        def handler(ev: StreamEvent):
            queue.put_nowait(ev)

        # 5) Async task that runs the core loop
        async def _run_loop_task():
            nonlocal final_ai, final_metadata, loop_error
            try:
                ai, metadata = await self._run_tool_loop(
                    messages, event_handler=handler
                )
                final_ai = ai
                final_metadata = metadata
            except Exception as e:
                loop_error = e
            finally:
                loop_done.set()

        loop_task = asyncio.create_task(_run_loop_task())

        # 6) Consume events from the queue as they arrive
        while True:
            # exit condition: loop finished and queue is empty
            if loop_done.is_set() and queue.empty():
                break

            try:
                ev: StreamEvent = await asyncio.wait_for(
                    queue.get(), timeout=QUEUE_TIMEOUT
                )
            except asyncio.TimeoutError:
                continue

            ev_type = ev.get("type")

            if ev_type != "tool_result":
                logger.info("STREAMING EVENT (%s): %s", ev_type, ev)
            else:
                # reduced logging
                logger.info("STREAMING EVENT (%s)...", ev_type)

            yield ev

        # 7) Ensure the tool loop task is done
        await loop_task

        # Propagate failure if the loop raised
        if loop_error is not None:
            raise loop_error

        # 8) Emit a single final_answer event
        full_answer = final_ai.content if final_ai is not None else ""

        final_event: StreamEvent = {
            "type": "final_answer",
            "answer": full_answer,
            "metadata": final_metadata,
        }
        logger.info("STREAMING EVENT (final_answer): %s", final_event)
        yield final_event

    async def _stream_llm_messages(self, messages: List[Any]):
        """
        Internal helper: stream text from the underlying LLM using .astream(...),
        normalizing provider-specific chunk formats into plain text pieces.

        This does NOT use tools; it just streams raw model output for the given
        message list.
        """
        async for chunk in self.llm.astream(messages):
            piece = ""

            content = getattr(chunk, "content", None)
            if isinstance(content, str):
                piece = content
            elif isinstance(content, list):
                # Some providers return a list of parts; extract the text.
                parts = []
                for c in content:
                    text = None
                    if isinstance(c, dict):
                        text = c.get("text") or ""
                    else:
                        text = getattr(c, "text", "") or ""
                    if text:
                        parts.append(text)
                piece = "".join(parts)
            else:
                # Fallback: try .delta if present
                delta = getattr(chunk, "delta", None)
                if isinstance(delta, str):
                    piece = delta

            if not piece:
                continue

            yield piece

    async def stream_text_only(self, question: str):
        """
        Experimental helper: stream ONLY a plain LLM answer (no tools),
        using the underlying model's .astream(...) interface.

        This does NOT use the MCP tools or the agent loop:
        - builds [SystemMessage, HumanMessage]
        - calls self.llm.astream(...) via _stream_llm_messages(...)
        - yields text chunks as they arrive
        """
        system_prompt = build_system_prompt()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=question),
        ]

        async for piece in self._stream_llm_messages(messages):
            yield piece


#
# run methods
#
async def run(question: str, history):
    """
    Manage the non streaming case
    """
    agent = await AgentWithMCP.create()

    return await agent.answer(question, history)


async def run_streaming(question: str, history):
    """
    Streaming wrapper for the agent.

    Currently:
    - creates the agent
    - delegates to `answer_streaming`
    - exposes an async generator of events
    """
    agent = await AgentWithMCP.create()

    async for event in agent.answer_streaming(question, history):
        yield event


def run_streaming_sync(
    question: str,
    history,
    on_event: Callable[[StreamEvent], None],
) -> None:
    """
    Synchronous wrapper around the async streaming API.

    Usage pattern (e.g. in Streamlit or any sync code):

        def handle_event(ev: StreamEvent):
            # update UI, print, etc.
            ...

        run_streaming_sync("ciao", history=[], on_event=handle_event)

    This function:
    - runs the async generator `run_streaming(...)` inside asyncio.run
    - forwards each event to the provided `on_event` callback
    """

    async def _driver():
        async for ev in run_streaming(question, history):
            on_event(ev)

    asyncio.run(_driver())
