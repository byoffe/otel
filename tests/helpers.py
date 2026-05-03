"""Shared assertion helpers for OTEL tests."""

from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


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
