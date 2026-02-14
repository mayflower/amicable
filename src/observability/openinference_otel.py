from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialized = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _otlp_traces_endpoint() -> str:
    return (
        os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        or ""
    ).strip()


def _load_openinference_components() -> tuple[Any, Any]:
    from openinference.instrumentation import TraceConfig
    from openinference.instrumentation.langchain import LangChainInstrumentor

    return TraceConfig, LangChainInstrumentor


def _load_otel_components() -> tuple[Any, Any, Any, Any]:
    from opentelemetry import trace as trace_api
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk import trace as trace_sdk
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    return trace_api, OTLPSpanExporter, trace_sdk, BatchSpanProcessor


def init_openinference_langchain_otel() -> bool:
    """Initialize OpenInference LangChain tracing once (fail-open)."""
    global _initialized

    if not _env_bool("AMICABLE_OTEL_ENABLED", False):
        return False
    if _initialized:
        return True

    with _init_lock:
        if _initialized:
            return True

        endpoint = _otlp_traces_endpoint()
        if not endpoint:
            logger.warning(
                "OpenInference OTEL is enabled but no OTLP endpoint is configured; "
                "set OTEL_EXPORTER_OTLP_TRACES_ENDPOINT (or OTEL_EXPORTER_OTLP_ENDPOINT)."
            )
            return False

        try:
            trace_config_cls, langchain_instrumentor_cls = (
                _load_openinference_components()
            )
            trace_api, otlp_span_exporter_cls, trace_sdk, batch_span_processor_cls = (
                _load_otel_components()
            )
        except Exception:
            logger.warning(
                "OpenInference OTEL dependencies unavailable; tracing stays disabled",
                exc_info=True,
            )
            return False

        try:
            current_provider = trace_api.get_tracer_provider()
            if isinstance(current_provider, trace_sdk.TracerProvider):
                tracer_provider = current_provider
            else:
                tracer_provider = trace_sdk.TracerProvider()
                trace_api.set_tracer_provider(tracer_provider)

            tracer_provider.add_span_processor(
                batch_span_processor_cls(otlp_span_exporter_cls())
            )

            langchain_instrumentor_cls().instrument(
                tracer_provider=tracer_provider,
                config=trace_config_cls(),
            )
            _initialized = True
            logger.info(
                "OpenInference LangChain OTEL instrumentation initialized (endpoint=%s)",
                endpoint,
            )
            return True
        except Exception:
            logger.warning(
                "Failed to initialize OpenInference LangChain OTEL; tracing stays disabled",
                exc_info=True,
            )
            return False
