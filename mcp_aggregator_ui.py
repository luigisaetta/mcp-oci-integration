"""
mcp_aggregator_ui.py
Streamlit UI for MCP Aggregator backends and call history.

Features
- Reads aggregator_config.yaml (path selectable in the sidebar)
- Lists all configured backends (name, URL), with tool count or error
- Per-backend expanders listing tools
- Per-tool expanders with description, inputSchema, outputSchema
- Shows aggregated MCP call history, duration, and status (OK/KO)
- Refresh button; concurrent discovery with asyncio
- Optional JWT auth via your default_jwt_supplier (honors enable_jwt_tokens in YAML)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
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


def load_config(
    path: str,
) -> Tuple[List[Backend], float, bool, str, str, Dict[str, Any]]:
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
    aggregator_url = str(cfg.get("aggregator_url", "http://localhost:6000/mcp"))
    call_log_path = str(cfg.get("call_log_path", "logs/mcp_aggregator_calls.jsonl"))
    return (
        [Backend(name=b["name"], url=b["url"]) for b in backends_cfg],
        timeout,
        enable_jwt,
        aggregator_url,
        call_log_path,
        cfg,
    )


def load_call_records(log_path: str, limit: int = 300) -> List[Dict[str, Any]]:
    """
    Read tail records from the aggregator JSONL call log.
    """
    path = Path(log_path)
    if not path.exists():
        return []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    rows: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    rows.reverse()
    return rows


def build_jwt_auth(use_jwt: bool) -> Tuple[Optional[str], Optional[str]]:
    """
    Build JWT auth token for FastMCP client calls.
    """
    if not use_jwt:
        return None, None
    if default_jwt_supplier is None:
        return None, "JWT requested but default_jwt_supplier is not available"
    try:
        return default_jwt_supplier(), None
    except Exception as exc:
        return None, str(exc)


def _normalize_tool_response(res: Any) -> Any:
    """
    Normalize FastMCP call_tool response object.
    """
    val = getattr(res, "data", None)
    if val is not None:
        return val
    txt = getattr(res, "text", None)
    if txt is not None and txt != "":
        return txt
    parts = getattr(res, "content", None) or []
    texts = [getattr(p, "text", None) for p in parts if getattr(p, "text", None)]
    return "\n".join(texts) if texts else None


async def fetch_call_records_from_aggregator(
    aggregator_url: str,
    timeout: float,
    auth_supplier,
    limit: int,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetch recent call records from the remote aggregator.
    """
    try:
        async with Client(
            aggregator_url,
            timeout=timeout,
            auth=auth_supplier if auth_supplier else None,
        ) as client:
            res = await client.call_tool("mcp_aggregator_call_history", {"limit": limit})

        payload = _normalize_tool_response(res)
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload["items"], None
        if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
            result = payload["result"]
            if isinstance(result.get("items"), list):
                return result["items"], None
        return [], "Unexpected response from mcp_aggregator_call_history"
    except Exception as exc:
        return [], str(exc)


async def fetch_tools_from_aggregator(
    aggregator_url: str,
    timeout: float,
    auth_supplier,
    backends: List[Backend],
    use_namespace: bool,
) -> Tuple[List[BackendResult], Optional[str], int]:
    """
    Discover tools through the aggregator endpoint instead of direct backend URLs.
    """
    try:
        async with Client(
            aggregator_url,
            timeout=timeout,
            auth=auth_supplier if auth_supplier else None,
        ) as client:
            tools = await client.list_tools()
    except Exception as exc:
        return [], str(exc), 0

    by_backend: Dict[str, List[ToolInfo]] = {b.name: [] for b in backends}
    backend_names = set(by_backend.keys())

    def to_plain(x):
        if x is None:
            return None
        if isinstance(x, dict):
            return x
        try:
            return x.model_dump()  # type: ignore[attr-defined]
        except Exception:
            try:
                return json.loads(json.dumps(x, default=_safe_default))
            except Exception:
                return {"_warning": "unserializable schema"}

    unmapped_count = 0
    for t in tools:
        full_name = getattr(t, "name", "unknown")
        if full_name.startswith("mcp_aggregator_"):
            continue

        desc = getattr(t, "description", None)
        in_schema = getattr(t, "inputSchema", None)
        out_schema = getattr(t, "outputSchema", None)

        target_backend: Optional[str] = None
        shown_name = full_name

        # Try namespace mapping first, regardless of local config value.
        if "." in full_name:
            maybe_backend, maybe_tool = full_name.split(".", 1)
            if maybe_backend in backend_names:
                target_backend = maybe_backend
                shown_name = maybe_tool

        if target_backend is None:
            for b in backends:
                if desc and f"Proxy to {b.name}:" in desc:
                    target_backend = b.name
                    break

        if target_backend is None:
            unmapped_count += 1
            continue

        by_backend[target_backend].append(
            ToolInfo(
                name=shown_name,
                description=desc,
                input_schema=to_plain(in_schema),
                output_schema=to_plain(out_schema),
            )
        )

    results = [
        BackendResult(backend=b, tools=by_backend.get(b.name, []), error=None)
        for b in backends
    ]
    return results, None, unmapped_count


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

# Load config
DEFAULT_CFG_PATH = "aggregator_config.yaml"
with st.sidebar:
    st.header("Configuration")
    cfg_path = st.text_input("Path to aggregator_config.yaml", value=DEFAULT_CFG_PATH)

try:
    backends, timeout, enable_jwt, aggregator_url, call_log_path, cfg = load_config(
        cfg_path
    )
except Exception as e:
    st.error(f"Failed to load config: {e}")
    st.stop()

with st.sidebar:
    st.text_input(label="timeout", value=timeout, disabled=True)
    st.text_input(label="enable_jwt", value=enable_jwt, disabled=True)
    use_namespace = bool(cfg.get("use_namespace", False))
    st.text_input(label="use_namespace", value=use_namespace, disabled=True)
    aggregator_url = st.text_input(label="aggregator_url", value=aggregator_url)
    use_aggregator_jwt = st.checkbox(
        "Use JWT for aggregator", value=bool(enable_jwt)
    )
    st.text_input(label="call_log_path", value=call_log_path, disabled=True)
    log_rows = st.slider("Recent call rows", min_value=50, max_value=2000, value=300)
    discover_via_aggregator = st.checkbox(
        "Discover tools via aggregator", value=True
    )

    do_refresh = st.button("Refresh", type="primary")
    st.markdown("---")


# Cache discovery keyed by a deterministic signature
@st.cache_data(show_spinner=True)
def _cached_discovery(_cfg_sig: str) -> List[BackendResult]:
    return asyncio.run(discover_all(backends, timeout, enable_jwt, cfg))


@st.cache_data(show_spinner=True)
def _cached_aggregator_discovery(
    _cfg_sig: str,
    _aggregator_url: str,
    _use_namespace: bool,
    _use_aggregator_jwt: bool,
) -> Tuple[List[BackendResult], Optional[str], int]:
    auth_supplier, auth_error = build_jwt_auth(_use_aggregator_jwt)
    if auth_error:
        return [], auth_error, 0
    return asyncio.run(
        fetch_tools_from_aggregator(
            aggregator_url=_aggregator_url,
            timeout=timeout,
            auth_supplier=auth_supplier,
            backends=backends,
            use_namespace=_use_namespace,
        )
    )


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
    _cached_aggregator_discovery.clear()

if discover_via_aggregator:
    results, discovery_error, unmapped_tools = _cached_aggregator_discovery(
        cfg_signature, aggregator_url, use_namespace, use_aggregator_jwt
    )
else:
    results = _cached_discovery(cfg_signature)
    discovery_error = None
    unmapped_tools = 0

auth_supplier, auth_error = build_jwt_auth(use_aggregator_jwt)
if auth_error:
    remote_call_records = []
    remote_call_error = auth_error
else:
    remote_call_records, remote_call_error = asyncio.run(
        fetch_call_records_from_aggregator(
            aggregator_url=aggregator_url,
            timeout=timeout,
            auth_supplier=auth_supplier,
            limit=log_rows,
        )
    )
if remote_call_error:
    call_records = load_call_records(call_log_path, limit=log_rows)
else:
    call_records = remote_call_records

# High-level summary
cols = st.columns([2, 2, 2, 2, 2])
with cols[0]:
    st.metric("Configured backends", len(backends))
with cols[1]:
    total_tools = sum(len(r.tools) for r in results if not r.error)
    st.metric("Total tools discovered", total_tools)
with cols[2]:
    errors = sum(1 for r in results if r.error)
    st.metric("Backends with errors", errors)
with cols[3]:
    ok_calls = sum(1 for r in call_records if r.get("status") == "ok")
    st.metric("Calls OK", ok_calls)
with cols[4]:
    ko_calls = sum(1 for r in call_records if r.get("status") == "ko")
    st.metric("Calls KO", ko_calls)

st.markdown("---")

if discovery_error:
    st.warning(
        f"Tool discovery via aggregator failed (`{aggregator_url}`): {discovery_error}"
    )
    st.markdown("---")
elif unmapped_tools:
    st.caption(
        f"{unmapped_tools} discovered tool(s) could not be mapped to configured backends."
    )

# Recent MCP calls
st.subheader("Recent Aggregator Calls")
if not call_records:
    st.info("No call records found yet.")
else:
    rows = []
    for rec in call_records:
        status = rec.get("status", "").lower()
        rows.append(
            {
                "timestamp": rec.get("timestamp", ""),
                "status": "✅" if status == "ok" else "❌",
                "exposed_tool": rec.get("exposed_tool", ""),
                "backend": rec.get("backend", ""),
                "duration_ms": rec.get("duration_ms", ""),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)
if remote_call_error:
    st.caption(
        f"Remote history unavailable from `{aggregator_url}` ({remote_call_error}). Showing local file fallback."
    )
