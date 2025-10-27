"""
tracing_utils.py
----------------

Utility module to integrate OpenTelemetry tracing with **Oracle Cloud APM**
via the OTLP/HTTP exporter.

Features:
- Centralized initialization (reads from environment variables, supports explicit overrides).
- Uses OTLP/HTTP with "authorization: dataKey <KEY>" header for OCI APM ingestion.
- Supports both W3C Trace Context and B3 multi-header propagation.
- Optional auto-instrumentation for `requests` and logging.
- Provides convenient decorators and context managers for spans.

Typical usage:
---------------
from tracing_utils import setup_tracing, trace_span, start_span

setup_tracing(service_name="rag-backend")

@trace_span("rag.embed", model="cohere-embed-v4")
def embed(text: str): ...

with start_span("rag.query", rag_user_query="example"): ...
"""

import os
import atexit
from typing import Any, Dict, Optional, Callable
from functools import wraps

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

try:
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
except Exception:
    RequestsInstrumentor = None

try:
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
except Exception:
    LoggingInstrumentor = None

from config import ENABLE_TRACING

# 🔸 Global toggle
_INITIALIZED = False


def setup_tracing(
    service_name: Optional[str] = None,
    apm_traces_url: Optional[str] = None,
    data_key: Optional[str] = None,
    resource_attrs: Optional[Dict[str, Any]] = None,
    auto_instrument_requests: bool = True,
    auto_instrument_logging: bool = True,
    propagator: str = "tracecontext",
    sample_ratio: float = 1.0,
) -> None:
    """
    Initialize OpenTelemetry tracing and configure the OTLP/HTTP exporter to OCI APM.
    Tracing can be globally disabled with ENABLE_TRACING=false.
    """
    global _INITIALIZED

    if _INITIALIZED:
        return

    # 🔸 If tracing is disabled, set a NoOp provider and exit early
    if not ENABLE_TRACING:
        trace.set_tracer_provider(trace.NoOpTracerProvider())
        _INITIALIZED = True
        return

    service_name = service_name or os.getenv("OTEL_SERVICE_NAME", "rag-service")
    apm_traces_url = apm_traces_url or os.getenv("OCI_APM_TRACES_URL")
    data_key = data_key or os.getenv("OCI_APM_DATA_KEY")
    propagator = os.getenv("OTEL_PROPAGATORS", propagator)

    if not apm_traces_url:
        raise ValueError(
            "Missing APM endpoint. Set OCI_APM_TRACES_URL or pass it explicitly."
        )
    if not data_key:
        raise ValueError(
            "Missing OCI APM data key. Set OCI_APM_DATA_KEY or pass it explicitly."
        )

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    exporter = OTLPSpanExporter(
        endpoint=apm_traces_url,
        headers={"authorization": f"dataKey {data_key}"},
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    if propagator.lower().startswith("b3"):
        try:
            from opentelemetry.propagators.b3 import B3MultiFormat

            set_global_textmap(B3MultiFormat())
        except ImportError:
            set_global_textmap(TraceContextTextMapPropagator())
    else:
        set_global_textmap(TraceContextTextMapPropagator())

    if auto_instrument_requests and RequestsInstrumentor:
        RequestsInstrumentor().instrument()
    if auto_instrument_logging and LoggingInstrumentor:
        LoggingInstrumentor().instrument(set_logging_format=True)

    atexit.register(_shutdown_tracer_provider)
    _INITIALIZED = True


def get_tracer(name: Optional[str] = None):
    """Return a tracer instance for the given module or component."""
    return trace.get_tracer(name or __name__)


def start_span(name: str, **attrs):
    """
    Context manager for manual span creation.
    If tracing is disabled, acts as a no-op.
    """
    if not ENABLE_TRACING:
        # 🔸 Dummy no-op context manager
        class _NoOp:
            def __enter__(self):
                return None

            def __exit__(self, *args):
                return False

        return _NoOp()

    tracer = get_tracer()
    span_cm = tracer.start_as_current_span(name)
    span = span_cm.__enter__()
    for k, v in attrs.items():
        if v is not None:
            span.set_attribute(k, v)

    class _Closer:
        def __enter__(self):
            return span

        def __exit__(self, exc_type, exc, tb):
            if exc:
                span.record_exception(exc)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
            span_cm.__exit__(exc_type, exc, tb)

    return _Closer()


def trace_span(name: Optional[str] = None, **fixed_attrs):
    """
    Decorator that automatically creates a span around a function call.
    If tracing is disabled, it executes the function directly.
    """

    def _decorator(func: Callable):
        span_name = name or func.__name__

        @wraps(func)
        def _wrapped(*args, **kwargs):
            if not ENABLE_TRACING:
                return func(*args, **kwargs)

            tracer = get_tracer(func.__module__)
            with tracer.start_as_current_span(span_name) as span:
                for k, v in fixed_attrs.items():
                    if v is not None:
                        span.set_attribute(k, v)
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise

        return _wrapped

    return _decorator


def _shutdown_tracer_provider() -> None:
    """Flush and shut down the tracer provider cleanly."""
    if not ENABLE_TRACING:
        return
    provider = trace.get_tracer_provider()
    try:
        provider.shutdown()
    except Exception:
        pass
