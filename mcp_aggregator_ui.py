"""
mcp_aggregator_ui.py
Streamlit UI for MCP Aggregator backends (read-only, no changes to the aggregator required)

Features
- Reads aggregator_config.yaml (path selectable in the sidebar)
- Lists all configured backends (name, URL), with tool count or error
- Per-backend expanders listing tools
- Per-tool expanders with description, inputSchema, outputSchema
- Refresh button; concurrent discovery with asyncio
- Optional JWT auth via your default_jwt_supplier (honors enable_jwt_tokens in YAML)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import yaml

# fastmcp >= 2.x
from fastmcp import Client

# Optional JWT supplier (you already use this in the aggregator)
try:
    from llm_with_mcp import default_jwt_supplier
except Exception:
    default_jwt_supplier = None  # JWT disabled if not available


@dataclass
class Backend:
    """
    Represents a backend configured in the aggregator.
    """

    name: str
    url: str


@dataclass
class ToolInfo:
    """
    Represents a tool discovered from a backend.
    """

    name: str
    description: Optional[str]
    input_schema: Optional[Dict[str, Any]]
    output_schema: Optional[Dict[str, Any]]


@dataclass
class BackendResult:
    """
    Result of querying a backend for its tools.
    """

    backend: Backend
    tools: List[ToolInfo]
    error: Optional[str] = None


def load_config(path: str) -> Tuple[List[Backend], float, bool, Dict[str, Any]]:
    """
    Load aggregator_config.yaml and extract backends and settings.
    """
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    timeout = float(cfg.get("timeout_seconds", 15))
    backends_cfg = cfg.get("backends", []) or []
    if not backends_cfg:
        raise RuntimeError("No backends found in config.")

    enable_jwt = bool(cfg.get("enable_jwt_tokens", False))
    return (
        [Backend(name=b["name"], url=b["url"]) for b in backends_cfg],
        timeout,
        enable_jwt,
        cfg,
    )


def _safe_default(obj):
    """Best-effort conversion for weird schema objects."""
    try:
        return obj.__dict__
    except Exception:
        return str(obj)


async def fetch_backend_tools(
    backend: Backend,
    timeout: float,
    auth_supplier,
) -> BackendResult:
    """Query a single backend for its tools and schemas."""
    try:
        async with Client(
            backend.url,
            timeout=timeout,
            auth=auth_supplier if auth_supplier else None,
        ) as client:
            tools = await client.list_tools()

        results: List[ToolInfo] = []

        def to_plain(x):
            if x is None:
                return None
            if isinstance(x, dict):
                return x
            # Try Pydantic v2 or similar
            try:
                return x.model_dump()  # type: ignore[attr-defined]
            except Exception:
                # Fallback to JSON roundtrip
                try:
                    return json.loads(json.dumps(x, default=_safe_default))
                except Exception:
                    return {"_warning": "unserializable schema"}

        for t in tools:
            name = getattr(t, "name", "unknown")
            desc = getattr(t, "description", None)
            in_schema = getattr(t, "inputSchema", None)
            out_schema = getattr(t, "outputSchema", None)
            results.append(
                ToolInfo(
                    name=name,
                    description=desc,
                    input_schema=to_plain(in_schema),
                    output_schema=to_plain(out_schema),
                )
            )
        return BackendResult(backend=backend, tools=results, error=None)
    except Exception as e:
        return BackendResult(backend=backend, tools=[], error=str(e))


async def discover_all(
    backends: List[Backend],
    timeout: float,
    enable_jwt: bool,
    _cfg: Dict[str, Any],  # kept for future parity, not used directly
) -> List[BackendResult]:
    """Concurrent discovery across all backends."""
    auth_supplier = None
    if enable_jwt:
        if default_jwt_supplier is None:

            async def _missing_auth(*_args, **_kwargs):
                raise RuntimeError("JWT enabled but default_jwt_supplier not available")

            auth_supplier = _missing_auth  # triggers a clear error
        else:
            auth_supplier = default_jwt_supplier()

    tasks = [
        fetch_backend_tools(b, timeout=timeout, auth_supplier=auth_supplier)
        for b in backends
    ]
    return await asyncio.gather(*tasks)


# --------------------- Streamlit UI ---------------------
st.set_page_config(page_title="MCP Aggregator – Backends & Tools", layout="wide")
st.title("MCP Aggregator – Backends & Tools")

with st.sidebar:
    st.header("Configuration")
    cfg_path = st.text_input(
        "Path to aggregator_config.yaml", value="aggregator_config.yaml"
    )
    do_refresh = st.button("Refresh", type="primary")
    st.markdown("---")


# Load config
try:
    backends, timeout, enable_jwt, cfg = load_config(cfg_path)
except Exception as e:
    st.error(f"Failed to load config: {e}")
    st.stop()


# Cache discovery keyed by a deterministic signature
@st.cache_data(show_spinner=True)
def _cached_discovery(_cfg_sig: str) -> List[BackendResult]:
    return asyncio.run(discover_all(backends, timeout, enable_jwt, cfg))


cfg_signature = json.dumps(
    {
        "cfg_path": cfg_path,
        "timeout": timeout,
        "enable_jwt": enable_jwt,
        "backends": [b.__dict__ for b in backends],
    },
    sort_keys=True,
)

if do_refresh:
    _cached_discovery.clear()

results = _cached_discovery(cfg_signature)

# High-level summary
cols = st.columns([2, 2, 2])
with cols[0]:
    st.metric("Configured backends", len(backends))
with cols[1]:
    total_tools = sum(len(r.tools) for r in results if not r.error)
    st.metric("Total tools discovered", total_tools)
with cols[2]:
    errors = sum(1 for r in results if r.error)
    st.metric("Backends with errors", errors)

st.markdown("---")

# Per-backend panels
for r in results:
    header_cols = st.columns([4, 5, 2])
    with header_cols[0]:
        st.subheader(r.backend.name)
    with header_cols[1]:
        st.code(r.backend.url, language="text")
    with header_cols[2]:
        if r.error:
            st.error("error")
        else:
            st.success(f"{len(r.tools)} tools")

    if r.error:
        with st.expander(f"Error details for {r.backend.name}", expanded=True):
            st.error(r.error)
        st.markdown("---")
        continue

    with st.expander(f"Tools in {r.backend.name}", expanded=False):
        # Quick table
        names = [t.name for t in r.tools]
        st.write(f"**{len(names)}** tools found:")
        st.dataframe({"tool_name": names}, width="stretch", hide_index=True)

        # Detailed per-tool expanders
        for t in r.tools:
            with st.expander(t.name, expanded=False):
                if t.description:
                    st.markdown(f"**Description**\n\n{t.description}")
                else:
                    st.markdown("_No description provided._")

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**Input Schema**")
                    st.json(t.input_schema if t.input_schema else {"_": "none"})
                with col_b:
                    st.markdown("**Output Schema**")
                    st.json(t.output_schema if t.output_schema else {"_": "none"})

    st.markdown("---")
