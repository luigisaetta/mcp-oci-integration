"""
tracing_utils.py
----------------

Utility module to integrate OpenTelemetry tracing with **Oracle Cloud APM**
via the OTLP/HTTP exporter.

Features:
- Centralized initialization (reads from environment variables, supports explicit overrides).
- Uses OTLP/HTTP with "authorization: dataKey <KEY>" header for OCI APM ingestion.
- Supports both W3C Trace Context and B3 multi-header propagation (B3 optional).
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
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Optional B3 propagator (install: `pip install opentelemetry-propagator-b3`)
try:
    # type: ignore[attr-defined]
    from opentelemetry.propagators.b3 import (
        B3MultiFormat,
    )  # pylint: disable=import-error
except Exception:  # pragma: no cover
    B3MultiFormat = None  # type: ignore

# Optional instrumentation modules
try:
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
except Exception:  # pragma: no cover
    RequestsInstrumentor = None

try:
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
except Exception:  # pragma: no cover
    LoggingInstrumentor = None

# global toggle for enabling/disabling tracing
from config import ENABLE_TRACING

_INITIALIZED = False


def setup_tracing(
    service_name: Optional[str] = None,
    apm_traces_url: Optional[str] = None,
    data_key: Optional[str] = None,
    resource_attrs: Optional[Dict[str, Any]] = None,
    auto_instrument_requests: bool = True,
    auto_instrument_logging: bool = True,
    propagator: str = "tracecontext",  # "tracecontext" | "b3multi"
    # 0.0..1.0 (will configure ParentBased(TraceIdRatioBased))
    sample_ratio: float = 1.0,
) -> None:
    """
    Initialize OpenTelemetry tracing and configure the OTLP/HTTP exporter to OCI APM.
    Tracing can be globally disabled with ENABLE_TRACING=false.

    Env vars (used if parameters are None):
        - OTEL_SERVICE_NAME
        - OCI_APM_TRACES_URL
        - OCI_APM_DATA_KEY
        - OTEL_PROPAGATORS  (e.g., "tracecontext" or "b3multi")

    Raises:
        ValueError: If required endpoint or data key is missing when tracing is enabled.
    """
    global _INITIALIZED

    if _INITIALIZED:
        return

    # If tracing is disabled, set a NoOp provider and exit early
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

    # Configure sampler (ParentBased + ratio); default is AlwaysOn if ratio >= 1.0
    sampler = None
    if 0.0 <= sample_ratio < 1.0:
        sampler = ParentBased(TraceIdRatioBased(sample_ratio))

    # Define service resource
    base_attrs = {"service.name": service_name}
    if resource_attrs:
        base_attrs.update(resource_attrs)

    provider = TracerProvider(resource=Resource.create(base_attrs), sampler=sampler)
    exporter = OTLPSpanExporter(
        endpoint=apm_traces_url,
        headers={"authorization": f"dataKey {data_key}"},
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Propagation selection
    if propagator.lower().startswith("b3") and B3MultiFormat is not None:
        set_global_textmap(B3MultiFormat())
    else:
        # Fallback to W3C Trace Context (works out of the box with OCI APM)
        set_global_textmap(TraceContextTextMapPropagator())

    # Optional auto-instrumentation
    if auto_instrument_requests and RequestsInstrumentor:
        RequestsInstrumentor().instrument()
    if auto_instrument_logging and LoggingInstrumentor:
        LoggingInstrumentor().instrument(set_logging_format=True)

    atexit.register(_shutdown_tracer_provider)
    _INITIALIZED = True


def get_tracer(name: Optional[str] = None):
    """
    Return a tracer instance for the given module or component.

    Args:
        name: The tracer name (usually __name__).
    """
    return trace.get_tracer(name or __name__)


def start_span(name: str, **attrs):
    """
    Context manager for manual span creation.
    If tracing is disabled, acts as a no-op.

    Usage:
        with start_span("rag.embed", model="cohere-embed-v4") as span:
            ...
    """
    if not ENABLE_TRACING:

        @contextmanager
        def _noop():
            yield None

        return _noop()

    tracer = get_tracer()

    @contextmanager
    def _span_context():
        # Proper context manager usage (no direct __enter__/__exit__ calls)
        with tracer.start_as_current_span(name) as span:
            # Attach provided attributes up-front
            for key, val in attrs.items():
                if val is not None:
                    span.set_attribute(key, val)
            try:
                yield span
            except Exception as exc:
                # Record exception and mark error status
                span.record_exception(exc)
                # Using trace.Status / StatusCode keeps compatibility across versions
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
                raise

    return _span_context()


def trace_span(name: Optional[str] = None, **fixed_attrs):
    """
    Decorator that automatically creates a span around a function call.
    If tracing is disabled, it executes the function directly.

    Example:
        @trace_span("rag.generate", llm_provider="gpt")
        def generate_answer(...): ...
    """

    def _decorator(func: Callable):
        span_name = name or func.__name__

        @wraps(func)
        def _wrapped(*args, **kwargs):
            if not ENABLE_TRACING:
                return func(*args, **kwargs)

            tracer = get_tracer(func.__module__)
            with tracer.start_as_current_span(span_name) as span:
                for key, val in fixed_attrs.items():
                    if val is not None:
                        span.set_attribute(key, val)
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
                    raise

        return _wrapped

    return _decorator


def _shutdown_tracer_provider() -> None:
    """Flush and shut down the tracer provider cleanly (no-op if tracing disabled)."""
    if not ENABLE_TRACING:
        return
    provider = trace.get_tracer_provider()
    try:
        provider.shutdown()
    except Exception:  # pragma: no cover
        pass
