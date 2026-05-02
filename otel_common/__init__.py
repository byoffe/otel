"""Shared OpenTelemetry SDK initialization for all services and scripts."""

from __future__ import annotations

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


def init_otel(service_name: str) -> None:
    """Configure TracerProvider, MeterProvider, and LoggerProvider with OTLP gRPC exporters.

    Reads OTEL_EXPORTER_OTLP_ENDPOINT from the environment (default: http://localhost:4317).
    Also bridges Python's standard logging module to the OTEL LoggerProvider so that
    logger.info(...) calls appear in Loki alongside traces and metrics.
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
    handler = LoggingHandler(level=logging.DEBUG, logger_provider=provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.DEBUG)
