"""
Streamlit UI for MCP servers
"""

import asyncio
import traceback
import streamlit as st

# added pdf upload
from pypdf import PdfReader

from config import MODEL_LIST, UI_TITLE, ENABLE_JWT_TOKEN
from mcp_servers_config import MCP_SERVERS_CONFIG

# this one contains the backend and the test code only for console
from llm_with_mcp import AgentWithMCP, default_jwt_supplier

from utils import get_console_logger

logger = get_console_logger()

# max chars in pdf
MAX_CHARS = 30000


# NEW: PDF -> text (no OCR)
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

# ---------- Sidebar: connection settings ----------
with st.sidebar:
    with st.sidebar.container():
        st.subheader("Connection")
        mcp_url = st.text_input("MCP URL", value=MCP_SERVERS_CONFIG["default"]["url"])

        timeout = st.number_input(
            "Timeout (s)", min_value=5, max_value=300, value=60, step=5
        )

    is_jwt_enable = st.toggle("Enable JWT tokens", value=ENABLE_JWT_TOKEN)

    st.divider()

    # ---------- Sidebar: LLM settings ----------
    with st.sidebar.container():
        st.subheader("LLM Model")
        model_id = st.selectbox(
            "Model",
            MODEL_LIST,
            index=0,
        )

        st.divider()

    # ---------- Sidebar: PDF ingestion (hidden context) ----------
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
                    # Guardrail: keep within your model context budget
                    # tune for your model/tokenizer

                    truncated = False
                    if len(raw_text) > MAX_CHARS:
                        raw_text = (
                            raw_text[:MAX_CHARS] + "\n\n...[Truncated for context size]"
                        )
                        truncated = True

                        # Optional: keep the full text for debugging/storage
                        st.session_state.last_pdf_text = (
                            # here it’s already truncated
                            raw_text
                        )

                    st.session_state.last_pdf_name = uploaded_pdf.name

                    # Inject as a HIDDEN user message so the LLM treats it as user-provided content
                    st.session_state.chat.append(
                        {
                            "role": "user",
                            "content": f"[Context from PDF: {uploaded_pdf.name}]\n{raw_text}",
                            # <-- key bit: do not render, but keep for the model
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

# ---------- Session state ----------
if "agent" not in st.session_state:
    st.session_state.agent = None
if "chat" not in st.session_state:
    # list of {"role": "user"|"assistant", "content": str}
    st.session_state.chat = []
if "last_pdf_name" not in st.session_state:
    st.session_state.last_pdf_name = None
if "last_pdf_text" not in st.session_state:
    st.session_state.last_pdf_text = None


def reset_conversation():
    """Reset the chat history."""
    st.session_state.chat = []


# ---------- Connect / reload ----------
if connect:
    with st.spinner("Connecting to MCP server and loading tools…"):
        try:
            # Create an agent (async factory) and cache it in session_state
            st.session_state.agent = asyncio.run(
                AgentWithMCP.create(
                    mcp_url=mcp_url,
                    # returns a fresh raw JWT
                    jwt_supplier=default_jwt_supplier,
                    timeout=timeout,
                    model_id=model_id,
                )
            )
            st.success("Connected. Tools loaded.")
        except Exception as e:
            st.session_state.agent = None
            st.error(f"Failed to connect: {e}")
            logger.error(e)
            STACK_STR = traceback.format_exc()
            logger.error(STACK_STR)

# Reset button
if st.sidebar.button("Clear Chat History"):
    reset_conversation()

# ---------- Chat history (display) ----------
for msg in st.session_state.chat:
    # NEW: hide messages explicitly marked as hidden
    if msg.get("hidden", False):
        # hidden is reserved to pdf text
        continue

    role = msg.get("role", "assistant")
    # Only render user/assistant
    if role not in ("user", "assistant"):
        continue

    with st.chat_message(role):
        st.write(msg.get("content", ""))

# ---------- Input box ----------
prompt = st.chat_input("Ask your question…")

if prompt:
    # Show the user message immediately
    st.session_state.chat.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    if st.session_state.agent is None:
        st.warning(
            "Not connected. Click ‘Connect / Reload tools’ in the sidebar first."
        )
    else:
        with st.chat_message("assistant"):
            with st.spinner("Thinking with support from MCP tools…"):
                try:
                    ANSWER = asyncio.run(
                        # we pass also the history (chat)
                        st.session_state.agent.answer(prompt, st.session_state.chat)
                    )
                except Exception as e:
                    ANSWER = f"Error: {e}"

                # escape $ in the answer to avoid Streamlit interpreting it as LaTeX
                ANSWER = ANSWER.replace("$", "\\$")

                st.write(ANSWER)
                st.session_state.chat.append({"role": "assistant", "content": ANSWER})

# ---------- The small debug panel in the bottom ----------
with st.expander("🔎 Debug / State"):
    st.json(
        {
            "connected": st.session_state.agent is not None,
            "messages_in_memory": len(st.session_state.chat),
            "mcp_url": mcp_url,
            "model_id": model_id,
            "timeout": timeout,
        }
    )
