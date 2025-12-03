"""
UI MCP Agent V2

With streaming support (02/12/2025)

A Streamlit-based UI for interacting with an LLM agent connected to an MCP server.
Streaming responses are supported, with tool call events displayed in real-time.

"""

import asyncio
from typing import Dict, Any
import traceback

import streamlit as st

from pypdf import PdfReader

from config import MODEL_LIST, UI_TITLE, ENABLE_JWT_TOKEN
from mcp_servers_config import MCP_SERVERS_CONFIG

from llm_with_mcp import AgentWithMCP, default_jwt_supplier
from utils import get_console_logger

logger = get_console_logger()

# ---------- some configs ----------
# max chars in pdf uploaded
MAX_CHARS = 30000
TIMEOUT = 60


def get_username():
    """Get the authenticated username from Streamlit headers, if available."""
    headers = st.context.headers
    return headers.get("X-Auth-User")


def _extract_text_from_pdf(uploaded_file) -> str:
    """
    Extract text from a PDF uploaded via Streamlit.
    Returns a single concatenated string.
    Scanned PDFs without text will return ''.
    """
    reader = PdfReader(uploaded_file)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


# ---------- Page setup ----------
st.set_page_config(page_title="MCP UI", page_icon="🛠️", layout="wide")
st.title(UI_TITLE)

# ---------- Session state ----------
if "agent" not in st.session_state:
    st.session_state.agent = None
if "chat" not in st.session_state:
    # list of {"role": "user"|"assistant", "content": str, "hidden"?: bool}
    st.session_state.chat = []
if "last_pdf_name" not in st.session_state:
    st.session_state.last_pdf_name = None
if "last_pdf_text" not in st.session_state:
    st.session_state.last_pdf_text = None
if "last_metadata" not in st.session_state:
    st.session_state.last_metadata = {}

answer_metadata = st.session_state.last_metadata

USER = get_username()
logger.info("Authenticated user: %s", USER)

# ---------- Sidebar ----------
with st.sidebar:
    with st.sidebar.container():
        st.subheader("Connection")
        mcp_url = st.text_input("MCP URL", value=MCP_SERVERS_CONFIG["default"]["url"])

    is_jwt_enable = st.toggle("Enable JWT tokens", value=ENABLE_JWT_TOKEN)

    st.divider()

    with st.sidebar.container():
        st.subheader("LLM Model")
        model_id = st.selectbox("Model", MODEL_LIST, index=0)

        st.divider()

    with st.sidebar.container():
        st.subheader("Document")
        uploaded_pdf = st.file_uploader("Upload PDF", type=["pdf"])
        add_pdf = st.button(
            "➕ Add PDF to context (hidden)",
            use_container_width=True,
            disabled=uploaded_pdf is None,
        )

        if add_pdf and uploaded_pdf is not None:
            try:
                raw_text = _extract_text_from_pdf(uploaded_pdf)

                if not raw_text:
                    st.warning("No extractable text found (scanned PDF or empty).")
                else:
                    truncated = False
                    if len(raw_text) > MAX_CHARS:
                        raw_text = (
                            raw_text[:MAX_CHARS] + "\n\n...[Truncated for context size]"
                        )
                        truncated = True

                    st.session_state.last_pdf_text = raw_text
                    st.session_state.last_pdf_name = uploaded_pdf.name

                    # Hidden user message for context
                    st.session_state.chat.append(
                        {
                            "role": "user",
                            "content": f"[Context from PDF: {uploaded_pdf.name}]\n{raw_text}",
                            "hidden": True,
                        }
                    )

                    note = f"Added '{uploaded_pdf.name}' to context (hidden)."
                    if truncated:
                        note += " (truncated)"
                    st.success(note)
            except Exception as e:
                st.error(f"Failed to read PDF: {e}")

        st.divider()

    connect = st.button("🔌 Connect / Reload tools", use_container_width=True)

    def reset_conversation():
        """
        Reset the chat history.
        """
        st.session_state.chat = []

    if st.button("Clear Chat History", use_container_width=True):
        reset_conversation()

# ---------- Connect / reload ----------
if connect:
    with st.spinner("Connecting to MCP server and loading tools…"):
        try:
            st.session_state.agent = asyncio.run(
                AgentWithMCP.create(
                    mcp_url=mcp_url,
                    jwt_supplier=default_jwt_supplier,
                    timeout=TIMEOUT,
                    model_id=model_id,
                )
            )
            st.success("Connected. Tools loaded.")
        except Exception as e:
            st.session_state.agent = None
            st.error(f"Failed to connect: {e}")
            logger.error(e)
            logger.error(traceback.format_exc())

# ---------- Chat history (display) ----------
for msg in st.session_state.chat:
    if msg.get("hidden", False):
        # do not render hidden context messages
        continue

    role = msg.get("role", "assistant")
    if role not in ("user", "assistant"):
        continue

    with st.chat_message(role):
        st.write(msg.get("content", ""))


# ---------- Streaming logic ----------
def run_query_with_streaming(prompt: str):
    """
    Use the AgentWithMCP in streaming mode:
    - show tool_call events as toast with the tool name
    - show a final assistant balloon with the full answer
    """
    history = st.session_state.chat
    agent: AgentWithMCP = st.session_state.agent

    # Append user message to history
    history.append({"role": "user", "content": prompt})

    # Final answer balloon placeholder
    assistant_container = st.chat_message("assistant")
    final_answer_placeholder = assistant_container.empty()

    # Optional container for transient tool events
    tool_events_container = st.container()

    # Buffer for metadata from final answer
    final_metadata: Dict[str, Any] = {}

    async def _driver():
        nonlocal final_metadata

        async for ev in agent.answer_streaming(prompt, history):
            t = ev["type"]

            if t == "start":
                # Nothing extra; user message already printed
                continue

            elif t == "tool_call":
                # Show a small assistant balloon with the tool name
                with tool_events_container:
                    tool_name = ev.get("tool", "<unknown>")
                    st.toast(f"🔧 Calling tool: `{tool_name}`")

            elif t == "tool_result":
                # We ignore the payload by design, but you could add a small tick:
                with tool_events_container:
                    tool_name = ev.get("tool", "<unknown>")
                    st.toast(f"✅ Tool `{tool_name}` completed.")

            elif t == "tool_error":
                with tool_events_container:
                    with st.chat_message("assistant"):
                        tool_name = ev.get("tool", "<unknown>")
                        err = ev.get("payload", "Unknown error")
                        st.markdown(f"⚠️ Tool `{tool_name}` error: {err}")

            elif t == "final_answer":
                answer_text = ev.get("answer", "") or ""
                # Escape $ to avoid LaTeX interpretation
                answer_text = answer_text.replace("$", "\\$")

                final_answer_placeholder.markdown(answer_text)
                history.append({"role": "assistant", "content": answer_text})

                final_metadata = ev.get("metadata", {}) or {}
                st.session_state.last_metadata = final_metadata

            else:
                # Unknown event type
                with tool_events_container:
                    with st.chat_message("assistant"):
                        st.markdown(f"⚠️ Unknown event: `{t}`")

    asyncio.run(_driver())


# ---------- Input box ----------
prompt = st.chat_input("Ask your question…")

if prompt:
    # Show the user message immediately
    with st.chat_message("user"):
        st.write(prompt)

    if st.session_state.agent is None:
        st.warning(
            "Not connected. Click ‘Connect / Reload tools’ in the sidebar first."
        )
    else:
        with st.spinner("Generating answer using MCP tools…"):
            run_query_with_streaming(prompt)

# ---------- Debug panel ----------
with st.expander("🔎 Debug / State"):
    st.json(
        {
            "connected": st.session_state.agent is not None,
            "messages_in_memory": len(st.session_state.chat),
            "mcp_url": mcp_url,
            "model_id": model_id,
            "timeout": TIMEOUT,
            "last_tooling_metadata": st.session_state.last_metadata,
        }
    )
