"""Global pytest configuration.

Loaded before any test module is imported, so env-var and OTEL setup here
takes effect when service modules run their module-level code.
"""

import os

# Services read these constants at import time — zero them out so tests run fast.
os.environ.setdefault("SIM_DELAY_MIN", "0")
os.environ.setdefault("SIM_DELAY_MAX", "0")
os.environ.setdefault("SIM_ERROR_RATE", "0")

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from opentelemetry import metrics, trace  # noqa: E402
from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,  # noqa: E402
)

# ---------------------------------------------------------------------------
# In-memory OTEL backend
#
# Must be set up at module level — before any service module is imported —
# so that service-level get_meter() / get_tracer() calls land on these
# providers rather than the default no-op ones.
# ---------------------------------------------------------------------------
_span_exporter = InMemorySpanExporter()
_tracer_provider = TracerProvider()
_tracer_provider.add_span_processor(SimpleSpanProcessor(_span_exporter))
trace.set_tracer_provider(_tracer_provider)

_metric_reader = InMemoryMetricReader()
_meter_provider = MeterProvider(metric_readers=[_metric_reader])
metrics.set_meter_provider(_meter_provider)

# Prevent init_otel from overriding the providers we just configured.
patch("otel_common.init_otel", MagicMock()).start()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def span_exporter():
    """In-memory span exporter, cleared around each test."""
    _span_exporter.clear()
    yield _span_exporter
    _span_exporter.clear()


@pytest.fixture()
def metric_reader():
    """In-memory metric reader.  Drains accumulated state before yielding so
    each test sees only the metrics produced during that test."""
    _metric_reader.get_metrics_data()  # drain prior state
    yield _metric_reader


# ---------------------------------------------------------------------------
# Assertion helpers (importable by test modules)
# ---------------------------------------------------------------------------


def find_span(exporter: InMemorySpanExporter, **attrs: object):
    """Return the first finished span whose attributes contain all of *attrs*."""
    return next(
        (
            s
            for s in exporter.get_finished_spans()
            if all((s.attributes or {}).get(k) == v for k, v in attrs.items())
        ),
        None,
    )


def emitted_metric_names(reader: InMemoryMetricReader) -> set[str]:
    """Return the set of metric names present in the reader."""
    data = reader.get_metrics_data()
    if data is None:
        return set()
    return {m.name for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics}
