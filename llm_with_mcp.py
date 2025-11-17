"""
Based on fastmcp library.
This one provide also support for security in MCP calls, using JWT token.

This is the backend for the Streamlit MCP UI.

15/09: the code is a bit long to handle some exceptions regarding tool calling
with all the non-cohere models through Langchain.
As for now, it is working fine with: Cohere, GPT and grok,
some problems with llama 3.3

27/10/2024: added APM tracing support
"""

import uuid
import json
import asyncio
import logging
from typing import List, Dict, Any, Callable, Sequence, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import oci

from fastmcp import Client as MCPClient
from pydantic import BaseModel, Field, create_model
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    messages_to_dict,
    AIMessageChunk,
)

# our code imports
from oci_jwt_client import OCIJWTClient
from oci_models import get_llm
from agent_system_prompt import AGENT_SYSTEM_PROMPT_TEMPLATE
from utils import get_console_logger

# to integrate with OCI APM tracing
from tracing_utils import setup_tracing, start_span

from config import (
    IAM_BASE_URL,
    ENABLE_JWT_TOKEN,
    DEBUG,
    OCI_APM_TRACES_URL,
    OTEL_SERVICE_NAME,
)
from config_private import SECRET_OCID, OCI_APM_DATA_KEY
from mcp_servers_config import MCP_SERVERS_CONFIG

from log_helpers import log_tool_schemas, log_history_tail, log_ai_tool_calls

# for debugging
if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("oci").setLevel(logging.DEBUG)
    oci.base_client.is_http_log_enabled(True)

logger = get_console_logger()

# ---- Config ----
# trim the history to max MAX_HISTORY msgs
MAX_HISTORY = 10

MCP_URL = MCP_SERVERS_CONFIG["default"]["url"]
TIMEOUT = 60
# the scope for the JWT token
SCOPE = "urn:opc:idm:__myscopes__"

# eventually you can taylor the SYSTEM prompt here
# to help identify the tools and their usage.
# modified to be compliant to OpenAI spec.

# Use this as a template. It will be formatted with today_long/today_iso.
SYSTEM_PROMPT_TEMPLATE = AGENT_SYSTEM_PROMPT_TEMPLATE


def default_jwt_supplier() -> str:
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
    return SYSTEM_PROMPT_TEMPLATE.format(today_long=today_long, today_iso=today_iso)


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
        jwt_supplier: Callable[[], str],
        timeout: int,
        llm,
    ):
        self.mcp_url = mcp_url
        self.jwt_supplier = jwt_supplier
        self.timeout = timeout
        self.llm = llm
        self.model_with_tools = None
        # optional: cache tools to avoid re-listing every run
        self._tools_cache = None

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
        jwt_supplier: Callable[[], str] = default_jwt_supplier,
        timeout: int = TIMEOUT,
        model_id: str = "xai.grok-4",
    ):
        """
        Async factory: fetch tools, bind them to the LLM, return a ready-to-use agent.
        Important: Avoids doing awaits in __init__.
        """
        # should return a LangChain Chat model supporting .bind_tools(...)
        llm = get_llm(model_id=model_id)
        # after, we call init()
        self = cls(mcp_url, jwt_supplier, timeout, llm)

        tools = await self._list_tools()
        if not tools:
            logger.warning("No tools discovered at %s", mcp_url)
        self._tools_cache = tools

        schemas = [self._tool_to_schema(t) for t in tools]

        # wrapped with schemas_to_pyd to solve compatibility issues with non-cohere models
        pyd_models = schemas_to_pydantic_models(schemas)

        if DEBUG:
            log_tool_schemas(pyd_models, self.logger)

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

    #
    # ---------- main loop ----------
    #
    async def answer(self, question: str, history: list = None) -> str:
        """
        Run the LLM+MCP loop until the model stops calling tools.
        """
        # add the SYSTEM PROMPT and current request
        messages = self._build_messages(
            history=history,
            system_prompt=build_system_prompt(),
            current_user_prompt=question,
        )

        with start_span("tool_calling_loop", model=self.llm.model_id):
            #
            # This is the tool-calling loop
            #
            while True:
                # added to integrate with APM tracing
                with start_span("llm_invoke", model=self.llm.model_id):
                    logger.info("Invoking LLM...")

                    ai: AIMessage = await self.model_with_tools.ainvoke(messages)

                    if DEBUG:
                        log_history_tail(messages, k=4, log=self.logger)
                        log_ai_tool_calls(ai, log=self.logger)

                    tool_calls = getattr(ai, "tool_calls", None) or []
                    if not tool_calls:
                        # Final answer
                        return ai.content

                    messages.append(ai)  # keep the AI msg that requested tools

                    # Execute tool calls and append ToolMessage for each
                    tool_msgs = []
                    for tc in tool_calls:
                        name = tc["name"]
                        args = tc.get("args") or {}
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
                                    # must match the call id
                                    tool_call_id=tc["id"],
                                    name=name,
                                )
                                messages.append(tm)

                            # this is for debugging, if needed
                            if DEBUG:
                                tool_msgs.append(tm)
                        except Exception as e:
                            messages.append(
                                ToolMessage(
                                    content=json.dumps({"error": str(e)}),
                                    tool_call_id=tc["id"],
                                    name=name,
                                )
                            )

    def _normalize_tool_calls(self, tcs: list[dict]) -> list[dict]:
        """Normalize tool_calls from streamed chunks into LC-friendly [{'id','name','args'}...]"""
        norm = []
        for tc in tcs or []:
            try:
                # LC style: {'id','name','args':{...}}
                if "name" in tc and "args" in tc:
                    _id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                    _name = tc["name"]
                    _args = tc.get("args") or {}
                    # ensure dict if someone passed string
                    if isinstance(_args, str):
                        try:
                            _args = json.loads(_args)
                        except Exception:
                            _args = {"__raw__": _args}
                    norm.append({"id": _id, "name": _name, "args": _args})
                    continue

                # OpenAI wire style: {'id','type':'function','function': {'name', 'arguments': '...json...'}}
                fn = tc.get("function", {})
                if fn and isinstance(fn, dict) and fn.get("name"):
                    _id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                    _name = fn.get("name")
                    args_raw = fn.get("arguments", "") or ""
                    try:
                        _args = (
                            json.loads(args_raw)
                            if isinstance(args_raw, str)
                            else args_raw
                        )
                    except Exception:
                        # if arguments is partial/invalid JSON, pass raw so the tool can fail clearly
                        _args = {"__raw__": args_raw}
                    norm.append({"id": _id, "name": _name, "args": _args})
                    continue

                # Fallback: unknown shape → skip (or include raw)
                # norm.append({"id": f"call_{uuid.uuid4().hex[:8]}", "name": tc.get("name",""), "args": {}})
            except Exception:
                # keep going; one bad tc shouldn't break the turn
                continue
        return norm

    def _log_msg_wire(self, msgs: list, tag: str):
        try:
            wire = messages_to_dict(msgs)
            brief = []
            for m in wire[-12:]:
                t = m.get("type")
                data = m.get("data", {}) or {}
                if t == "ai":
                    tc = len(m.get("tool_calls") or data.get("tool_calls") or [])
                    brief.append(
                        {"type": t, "tc": tc, "len": len(data.get("content") or "")}
                    )
                elif t == "tool":
                    brief.append({"type": t, "name": data.get("name")})
                else:
                    brief.append({"type": t})
            logger.info("WIRE:")
            logger.info("WIRE[%s]: %s", tag, brief)
        except Exception as e:
            logger.exception("WIRE[%s] failed: %s", tag, e)

    async def answer_stream(self, question: str, history: list = None):
        """Stream assistant responses while preserving tool-calling semantics.

        Yields dictionaries describing stream events:

        - {"type": "token", "text": "..."}            -> incremental model output
        - {"type": "tool_start", "name": "<tool>"}    -> immediately before tool execution
        - {"type": "tool_end", "name": "<tool>"}      -> after tool completion (success/fail)
        - {"type": "final"}                           -> when the agent turn is complete
        """

        def _content_to_text(content: Any) -> str:
            if not content:
                return ""
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict)
                    and part.get("type") == "text"
                    and isinstance(part.get("text"), str)
                )
            return str(content)

        messages = self._build_messages(
            history=history,
            system_prompt=build_system_prompt(),
            current_user_prompt=question,
        )

        with start_span("tool_calling_loop_stream", model=self.llm.model_id):
            while True:
                ai: AIMessage
                try:
                    aggregated_chunk: AIMessageChunk | None = None
                    streamed_any = False

                    with start_span("llm_astream", model=self.llm.model_id):
                        async for chunk in self.model_with_tools.astream(messages):
                            if not isinstance(chunk, AIMessageChunk):
                                if DEBUG:
                                    self.logger.debug(
                                        "Ignoring streamed payload of type %s",
                                        type(chunk),
                                    )
                                continue

                            streamed_any = True

                            text_piece = _content_to_text(chunk.content)
                            if text_piece:
                                yield {"type": "token", "text": text_piece}

                            aggregated_chunk = (
                                chunk
                                if aggregated_chunk is None
                                else aggregated_chunk + chunk
                            )

                    if aggregated_chunk is not None:
                        message = aggregated_chunk.to_message()
                        if isinstance(message, AIMessage):
                            ai = message
                        else:
                            ai = AIMessage(**message.dict())
                    else:
                        if not streamed_any:
                            raise RuntimeError("No streamed chunks received from LLM")
                        ai = AIMessage(content="")

                except Exception:
                    if DEBUG:
                        self.logger.exception(
                            "Streaming failed; falling back to non-streaming invoke"
                        )
                    with start_span("llm_ainvoke_fallback", model=self.llm.model_id):
                        ai = await self.model_with_tools.ainvoke(messages)
                        fallback_text = _content_to_text(ai.content)
                        if fallback_text:
                            yield {"type": "token", "text": fallback_text}

                tool_calls = getattr(ai, "tool_calls", None) or []
                if not tool_calls:
                    yield {"type": "final"}
                    return

                messages.append(ai)

                for tc in tool_calls:
                    name = tc.get("name")
                    args = tc.get("args") or {}
                    call_id = tc.get("id")
                    yield {"type": "tool_start", "name": name}
                    try:
                        with start_span("tool_call_stream", tool=name):
                            result = await self._call_tool(name, args)

                        payload = (
                            getattr(result, "data", None)
                            or getattr(result, "content", None)
                            or str(result)
                        )
                        tool_content = (
                            json.dumps(payload, ensure_ascii=False)
                            if isinstance(payload, (dict, list))
                            else str(payload)
                        )
                        messages.append(
                            ToolMessage(
                                content=tool_content,
                                tool_call_id=call_id,
                                name=name,
                            )
                        )
                    except Exception as exc:
                        messages.append(
                            ToolMessage(
                                content=json.dumps({"error": str(exc)}),
                                tool_call_id=call_id,
                                name=name,
                            )
                        )
                    finally:
                        yield {"type": "tool_end", "name": name}


# ---- Example CLI usage ----
# this code is good for CLI, not Streamlit. See ui_mcp_agent.py
async def run_stream(question: str, history):
    """
    Manage the streaming case
    """
    agent = await AgentWithMCP.create()

    print("")

    async for event in agent.answer_stream(question, history=history):
        if event["type"] == "token":
            print(event["text"], end="", flush=True)
        elif event["type"] == "tool_start":
            print(f"\n[tool » {event['name']}]")
        elif event["type"] == "tool_end":
            print(f"[/tool « {event['name']}]")
        elif event["type"] == "final":
            print("\n")


async def run(question: str, history):
    """
    Manage the non streaming case
    """
    agent = await AgentWithMCP.create()

    return await agent.answer(question, history)


#
# Added to debug roubles with streaming
#
async def debug_compare_nonstream_vs_stream(question: str, history: list | None = None):
    """
    DO NOT touch answer(). This creates a fresh Agent, builds the same base messages,
    then executes:
      A) non-streaming (.ainvoke) with tool loop (1 turn of tools)
      B) streaming (.astream) with tool loop
    and dumps the messages_to_dict wires before each model call.
    """
    history = history or []
    agent = await AgentWithMCP.create()

    # Build the identical base message stack once
    base_msgs = agent._build_messages(
        history=history,
        system_prompt=build_system_prompt(),
        current_user_prompt=question,
    )

    def dump_wire(tag, msgs):
        """Log a compact wire view of messages_to_dict(msgs)."""
        try:
            wire = messages_to_dict(msgs)
            brief = []
            for m in wire[-12:]:
                typ = m.get("type")
                data = m.get("data") or {}
                if typ == "ai":
                    tc = len(m.get("tool_calls") or data.get("tool_calls") or [])
                    clen = len((data.get("content") or ""))
                    brief.append({"type": typ, "tc": tc, "len": clen})
                elif typ == "tool":
                    brief.append({"type": typ, "name": data.get("name")})
                else:
                    brief.append({"type": typ})
            logger.info("WIRE[%s]: %s", tag, brief)
            return wire
        except Exception as e:
            logger.exception("dump_wire failed: %s", e)
            return None

    # ========== A) NON-STREAM ==========
    msgs_ns = list(base_msgs)
    dump_wire("NS pre-call-1", msgs_ns)

    ai1 = await agent.model_with_tools.ainvoke(msgs_ns)
    msgs_ns.append(ai1)

    tc1 = (
        getattr(ai1, "tool_calls", None)
        or ai1.additional_kwargs.get("tool_calls", [])
        or []
    )
    if tc1:
        # one tool turn
        for tc in tc1:
            res = await agent._call_tool(tc["name"], tc.get("args") or {})
            payload = (
                getattr(res, "data", None) or getattr(res, "content", None) or str(res)
            )
            tool_content = (
                json.dumps(payload, ensure_ascii=False)
                if isinstance(payload, (dict, list))
                else str(payload)
            )
            msgs_ns.append(
                ToolMessage(
                    content=tool_content, tool_call_id=tc["id"], name=tc["name"]
                )
            )

        dump_wire("NS pre-call-2", msgs_ns)
        ai2 = await agent.model_with_tools.ainvoke(msgs_ns)
        final_ns = ai2.content or ""
    else:
        # final in first turn
        final_ns = ai1.content or ""

    logger.info("NS FINAL LEN: %d", len(final_ns))

    # ========== B) STREAM (no UI), but same semantics ==========
    msgs_st = list(base_msgs)
    dump_wire("ST pre-call-1", msgs_st)

    # collect first assistant turn via streaming
    streamed_text = []
    raw_tc = []
    async for ch in agent.model_with_tools.astream(msgs_st):
        tcs = getattr(ch, "tool_calls", None)
        if not tcs:
            ak = getattr(ch, "additional_kwargs", {}) or {}
            tcs = ak.get("tool_calls") or []
        if tcs:
            raw_tc.extend(tcs)

        content = getattr(ch, "content", None)
        if isinstance(content, list):
            streamed_text.append(
                "".join(
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            )
        elif isinstance(content, str):
            streamed_text.append(content)

    # normalize streamed tool calls to LC shape
    def norm_tool_calls(tcs: list[dict]) -> list[dict]:
        out = []
        for tc in tcs or []:
            fn = tc.get("function") if isinstance(tc, dict) else None
            if fn and isinstance(fn, dict) and fn.get("name"):
                args_raw = fn.get("arguments") or ""
                try:
                    args = (
                        json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    )
                except Exception:
                    args = {"__raw__": args_raw}
                out.append(
                    {
                        "id": tc.get("id") or "call_stream_1",
                        "name": fn["name"],
                        "args": args,
                    }
                )
            elif isinstance(tc, dict) and tc.get("name") is not None:
                args = tc.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"__raw__": args}
                out.append(
                    {
                        "id": tc.get("id") or "call_stream_1",
                        "name": tc["name"],
                        "args": args,
                    }
                )
        return out

    tc1s = norm_tool_calls(raw_tc)

    if tc1s:
        # function-call envelope (NO text)
        msgs_st.append(
            AIMessage(
                content="".join(streamed_text),
                tool_calls=tc1s,
                additional_kwargs={"tool_calls": tc1s},
            )
        )
        # execute tools
        for tc in tc1s:
            res = await agent._call_tool(tc["name"], tc.get("args") or {})
            payload = (
                getattr(res, "data", None) or getattr(res, "content", None) or str(res)
            )
            tool_content = (
                json.dumps(payload, ensure_ascii=False)
                if isinstance(payload, (dict, list))
                else str(payload)
            )
            msgs_st.append(
                ToolMessage(
                    content=tool_content, tool_call_id=tc["id"], name=tc["name"]
                )
            )

        dump_wire("ST pre-call-2", msgs_st)
        ai2s = await agent.model_with_tools.ainvoke(msgs_st)
        final_st = ai2s.content or ""
    else:
        # final in first turn
        final_st = "".join(streamed_text)

    logger.info("ST FINAL LEN: %d", len(final_st))

    # ========== Compare ==========
    print("\n=== FINAL TEXT DIFF ===")
    print("NS length:", len(final_ns))
    print("ST length:", len(final_st))
    print("Lengths equal? ", len(final_ns) == len(final_st))
    if len(final_ns) != len(final_st):
        print("\n--- NS FINAL ---\n", final_ns[:1200])
        print("\n--- ST FINAL ---\n", final_st[:1200])


if __name__ == "__main__":
    # A single, multi-line prompt (triple quotes avoids accidental string concatenation issues)
    QUESTION = """
Give me top 20 compartments for usage (amount) in november 2025. Put all the data in a table. 
Consider the current usage and then do a linear forecast over all the month. 
In the table put the current usage and the forecasted. 
In addition to the table give the details regarding the computation for the forecast. 
In addition, before deciding the top 20, do some aggregation: 
* aggregate the costs for mgueury and devops and put the total under the name mgueury 
* aggregate the costs for omasalem and ADBAGENT and put the total under omasalem
* aggregate the costs for matwolf and ai-test-oke and put the result under the name matwolf
* aggregate the costs for lsaetta and lsaetta-apm and put the result under the name lsaetta. 

Add a final row to the table with the overall total
"""
    # Optional: start with an empty history; replace with your stored chat history if needed
    HISTORY = []

    result = asyncio.run(run(QUESTION, history=HISTORY))

    print(result)
