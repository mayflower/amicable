from __future__ import annotations

import importlib


def _reload_module():
    import src.observability.openinference_otel as openinference_otel

    return importlib.reload(openinference_otel)


def test_init_openinference_otel_disabled_noop(monkeypatch):
    monkeypatch.delenv("AMICABLE_OTEL_ENABLED", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    m = _reload_module()

    assert m.init_openinference_langchain_otel() is False


def test_init_openinference_otel_missing_packages_fail_open(monkeypatch, caplog):
    monkeypatch.setenv("AMICABLE_OTEL_ENABLED", "1")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://collector:4318/v1/traces"
    )
    m = _reload_module()

    def _raise_import_error():
        raise ImportError("missing openinference")

    monkeypatch.setattr(m, "_load_openinference_components", _raise_import_error)

    with caplog.at_level("WARNING"):
        assert m.init_openinference_langchain_otel() is False
    assert "dependencies unavailable" in caplog.text


def test_init_openinference_otel_idempotent(monkeypatch):
    monkeypatch.setenv("AMICABLE_OTEL_ENABLED", "1")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://collector:4318/v1/traces"
    )
    m = _reload_module()

    class FakeTracerProvider:
        def __init__(self):
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class FakeTraceSDK:
        TracerProvider = FakeTracerProvider

    class FakeTraceAPI:
        def __init__(self):
            self.provider = object()
            self.set_calls = 0

        def get_tracer_provider(self):
            return self.provider

        def set_tracer_provider(self, provider):
            self.provider = provider
            self.set_calls += 1

    class FakeOTLPSpanExporter:
        calls = 0

        def __init__(self):
            FakeOTLPSpanExporter.calls += 1

    class FakeBatchSpanProcessor:
        calls = 0

        def __init__(self, _exporter):
            FakeBatchSpanProcessor.calls += 1

    class FakeTraceConfig:
        pass

    class FakeInstrumentor:
        calls = 0

        def instrument(self, **_kwargs):
            FakeInstrumentor.calls += 1

    fake_trace_api = FakeTraceAPI()
    monkeypatch.setattr(
        m,
        "_load_otel_components",
        lambda: (
            fake_trace_api,
            FakeOTLPSpanExporter,
            FakeTraceSDK,
            FakeBatchSpanProcessor,
        ),
    )
    monkeypatch.setattr(
        m,
        "_load_openinference_components",
        lambda: (FakeTraceConfig, FakeInstrumentor),
    )

    assert m.init_openinference_langchain_otel() is True
    assert m.init_openinference_langchain_otel() is True

    assert FakeInstrumentor.calls == 1
    assert FakeOTLPSpanExporter.calls == 1
    assert FakeBatchSpanProcessor.calls == 1


def test_init_openinference_otel_traceconfig_uses_env(monkeypatch):
    monkeypatch.setenv("AMICABLE_OTEL_ENABLED", "1")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://collector:4318/v1/traces"
    )
    monkeypatch.setenv("OPENINFERENCE_HIDE_INPUT_TEXT", "true")
    monkeypatch.setenv("OPENINFERENCE_HIDE_OUTPUT_TEXT", "true")
    monkeypatch.setenv("OPENINFERENCE_HIDE_INPUT_IMAGES", "true")
    m = _reload_module()

    class FakeTracerProvider:
        def add_span_processor(self, _processor):
            return None

    class FakeTraceSDK:
        TracerProvider = FakeTracerProvider

    class FakeTraceAPI:
        def __init__(self):
            self.provider = object()

        def get_tracer_provider(self):
            return self.provider

        def set_tracer_provider(self, provider):
            self.provider = provider

    class FakeOTLPSpanExporter:
        pass

    class FakeBatchSpanProcessor:
        def __init__(self, _exporter):
            return None

    class FakeTraceConfig:
        def __init__(self):
            import os

            self.hide_input_text = (
                (os.environ.get("OPENINFERENCE_HIDE_INPUT_TEXT") or "").lower()
                == "true"
            )
            self.hide_output_text = (
                (os.environ.get("OPENINFERENCE_HIDE_OUTPUT_TEXT") or "").lower()
                == "true"
            )
            self.hide_input_images = (
                (os.environ.get("OPENINFERENCE_HIDE_INPUT_IMAGES") or "").lower()
                == "true"
            )

    class FakeInstrumentor:
        last_config = None

        def instrument(self, **kwargs):
            FakeInstrumentor.last_config = kwargs.get("config")

    monkeypatch.setattr(
        m,
        "_load_otel_components",
        lambda: (
            FakeTraceAPI(),
            FakeOTLPSpanExporter,
            FakeTraceSDK,
            FakeBatchSpanProcessor,
        ),
    )
    monkeypatch.setattr(
        m,
        "_load_openinference_components",
        lambda: (FakeTraceConfig, FakeInstrumentor),
    )

    assert m.init_openinference_langchain_otel() is True
    cfg = FakeInstrumentor.last_config
    assert cfg is not None
    assert cfg.hide_input_text is True
    assert cfg.hide_output_text is True
    assert cfg.hide_input_images is True
