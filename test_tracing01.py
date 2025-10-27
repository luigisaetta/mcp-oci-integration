"""
Test tracing integration with simulated RAG workflow.
"""

from tracing_utils import setup_tracing, start_span, trace_span
from config import OCI_APM_TRACES_URL, OTEL_SERVICE_NAME
from config_private import OCI_APM_DATA_KEY

# Initialize once at startup
setup_tracing(
    service_name=OTEL_SERVICE_NAME,
    # Optionally, you can provide these explicitly instead of env vars:
    apm_traces_url=OCI_APM_TRACES_URL,
    data_key=OCI_APM_DATA_KEY,
    propagator="tracecontext",
)


@trace_span("rag.embed", model="cohere-embed-v4")
def embed(text: str):
    """
    simulate embed call
    """
    # Simulate model call
    return [0.12, 0.33]


@trace_span("rag.vector_search", db_system="oracle", oracle_selectai=True)
def vector_search(vec):
    """
    simulate vector search
    """
    return [{"id": "doc-42", "score": 0.91}]


@trace_span("rag.generate", llm_provider="gpt")
def generate(docs, query: str):
    """
    simulate generation
    """
    return f"Response for '{query}' ({len(docs)} docs)"


def rag_query(user_query: str):
    """
    simulate a RAG query with tracing
    """
    with start_span("test01", rag_user_query=user_query):
        v = embed(user_query)
        docs = vector_search(v)
        return generate(docs, user_query)


if __name__ == "__main__":
    print(rag_query("Explain caching in Text2SQL"))
