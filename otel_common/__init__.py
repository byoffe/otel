"""Shared OpenTelemetry SDK initialization for all services and scripts."""

from __future__ import annotations

import json
import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_DEFAULT_ENDPOINT = "http://localhost:4317"


class _TraceContextFilter(logging.Filter):
    """Injects trace_id and span_id from the active span into every LogRecord.

    This makes trace IDs available to formatters so they appear in the log body,
    enabling Grafana's log-to-trace correlation via derived fields regex.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        span = trace.get_current_span()
        ctx = span.get_span_context()
        # setattr avoids pyright complaints about unknown LogRecord attributes
        setattr(record, "trace_id", format(ctx.trace_id, "032x") if ctx.is_valid else "0" * 32)
        setattr(record, "span_id", format(ctx.span_id, "016x") if ctx.is_valid else "0" * 16)
        return True


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON with trace context embedded.

    Output: {"service":"…","level":"…","msg":"…","trace_id":"…","span_id":"…"}
    The trace_id field is extracted by Grafana's Loki derived-field regex for
    one-click log → trace navigation.
    """

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "service": record.name,
                "level": record.levelname,
                "msg": record.getMessage(),
                "trace_id": getattr(record, "trace_id", "0" * 32),
                "span_id": getattr(record, "span_id", "0" * 16),
            }
        )


def init_otel(service_name: str) -> None:
    """Configure TracerProvider, MeterProvider, and LoggerProvider with OTLP gRPC exporters.

    Reads OTEL_EXPORTER_OTLP_ENDPOINT from the environment (default: http://localhost:4317).
    Bridges Python's standard logging to OTEL (→ Loki) and to stdout as structured JSON
    (→ docker compose logs).  Both paths embed trace_id for correlation.
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_ENDPOINT)
    resource = Resource.create({"service.name": service_name})

    _setup_traces(endpoint, resource)
    _setup_metrics(endpoint, resource)
    _setup_logs(endpoint, resource)


def _setup_traces(endpoint: str, resource: Resource) -> None:
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)


def _setup_metrics(endpoint: str, resource: Resource) -> None:
    reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint))
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)


def _setup_logs(endpoint: str, resource: Resource) -> None:
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint)))
    set_logger_provider(provider)

    # OTLP path: Python log records → Collector → Loki
    otlp_handler = LoggingHandler(level=logging.DEBUG, logger_provider=provider)

    # Stdout path: JSON with trace_id → visible in `docker compose logs <svc>`
    stdout_handler = logging.StreamHandler()
    stdout_handler.addFilter(_TraceContextFilter())
    stdout_handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.addHandler(otlp_handler)
    root.addHandler(stdout_handler)
    root.setLevel(logging.DEBUG)
