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

import json
import asyncio
import logging
from typing import List, Dict, Any, Callable, Sequence, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import oci

from fastmcp import Client as MCPClient
from pydantic import BaseModel, Field, create_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

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
        model_id: str = "cohere.command-a-03-2025",
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


# ---- Example CLI usage ----
# this code is good for CLI, not Streamlit. See ui_mcp_agent.py
if __name__ == "__main__":
    QUESTION = "Tell me about Luigi Saetta. I need his e-mail address also."
    agent = asyncio.run(AgentWithMCP.create())
    print(asyncio.run(agent.answer(QUESTION)))
