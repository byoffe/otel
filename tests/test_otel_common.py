"""Tests for otel_common helper classes."""

import json
import logging
from unittest.mock import patch

import pytest
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from otel_common import _JsonFormatter, _TraceContextFilter


@pytest.fixture()
def log_record() -> logging.LogRecord:
    record = logging.LogRecord(
        name="test-svc",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="something happened",
        args=(),
        exc_info=None,
    )
    return record


class TestTraceContextFilter:
    def test_always_returns_true(self, log_record: logging.LogRecord) -> None:
        assert _TraceContextFilter().filter(log_record) is True

    def test_no_active_span_sets_zero_ids(self, log_record: logging.LogRecord) -> None:
        _TraceContextFilter().filter(log_record)
        assert log_record.trace_id == "0" * 32  # type: ignore[attr-defined]
        assert log_record.span_id == "0" * 16  # type: ignore[attr-defined]

    def test_active_span_injects_hex_ids(self, log_record: logging.LogRecord) -> None:
        ctx = SpanContext(
            trace_id=0xDEADBEEF1234567890ABCDEF12345678,
            span_id=0xCAFEBABE12345678,
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        mock_span = NonRecordingSpan(ctx)
        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            _TraceContextFilter().filter(log_record)
        assert log_record.trace_id == format(ctx.trace_id, "032x")  # type: ignore[attr-defined]
        assert log_record.span_id == format(ctx.span_id, "016x")  # type: ignore[attr-defined]


class TestJsonFormatter:
    def test_output_is_valid_json(self, log_record: logging.LogRecord) -> None:
        _TraceContextFilter().filter(log_record)
        output = _JsonFormatter().format(log_record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_required_fields_present(self, log_record: logging.LogRecord) -> None:
        _TraceContextFilter().filter(log_record)
        parsed = json.loads(_JsonFormatter().format(log_record))
        assert set(parsed.keys()) == {"service", "level", "msg", "trace_id", "span_id"}

    def test_service_and_level(self, log_record: logging.LogRecord) -> None:
        _TraceContextFilter().filter(log_record)
        parsed = json.loads(_JsonFormatter().format(log_record))
        assert parsed["service"] == "test-svc"
        assert parsed["level"] == "INFO"
        assert parsed["msg"] == "something happened"

    def test_trace_ids_are_strings(self, log_record: logging.LogRecord) -> None:
        _TraceContextFilter().filter(log_record)
        parsed = json.loads(_JsonFormatter().format(log_record))
        assert isinstance(parsed["trace_id"], str)
        assert isinstance(parsed["span_id"], str)
