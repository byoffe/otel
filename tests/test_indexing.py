"""Tests for the indexing service — span attributes, metric emission, error status."""

from fastapi.testclient import TestClient
from helpers import emitted_metric_names, find_span
from opentelemetry.trace import StatusCode

from services.indexing import main as indexing_module
from services.indexing.main import app

client = TestClient(app)

BAKED_BODY = {
    "transcript_id": "t-idx-001",
    "text": "hello world this is a test",
    "speakers": [{"name": "Alice", "word_count": 6}],
    "baked_tags": ["engineering", "planning"],
    "baked_summary": "A planning session",
}


# --- span assertions -------------------------------------------------------


def test_span_records_model(span_exporter):
    client.post("/index", json=BAKED_BODY)
    span = find_span(span_exporter, **{"indexing.model": "gpt-simulation-v1"})
    assert span is not None, "expected span with indexing.model attribute"


def test_span_records_token_count(span_exporter):
    # 6 words × 2 = 12 tokens
    client.post("/index", json=BAKED_BODY)
    span = find_span(span_exporter, **{"indexing.tokens_used": 12})
    assert span is not None, "expected span with indexing.tokens_used=12"


def test_error_span_on_simulated_failure(span_exporter, monkeypatch):
    monkeypatch.setattr(indexing_module, "_ERROR_RATE", 1.0)
    client.post("/index", json={**BAKED_BODY, "baked_tags": None, "baked_summary": None})
    error_spans = [
        s for s in span_exporter.get_finished_spans() if s.status.status_code == StatusCode.ERROR
    ]
    assert error_spans, "expected at least one span with ERROR status"


# --- metric assertions ------------------------------------------------------


def test_token_histogram_emitted(metric_reader):
    client.post("/index", json=BAKED_BODY)
    assert "indexing.llm_tokens_used" in emitted_metric_names(metric_reader)


def test_histogram_records_token_value(metric_reader):
    client.post("/index", json=BAKED_BODY)
    data = metric_reader.get_metrics_data()
    metric = next(
        m
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "indexing.llm_tokens_used"
    )
    total_sum = sum(dp.sum for dp in metric.data.data_points)
    assert total_sum > 0


# --- interaction assertions -------------------------------------------------


def test_baked_tags_and_summary_returned():
    r = client.post("/index", json=BAKED_BODY)
    assert r.status_code == 200
    assert r.json()["tags"] == ["engineering", "planning"]
    assert r.json()["summary"] == "A planning session"


def test_simulated_failure_returns_503(monkeypatch):
    monkeypatch.setattr(indexing_module, "_ERROR_RATE", 1.0)
    r = client.post("/index", json={**BAKED_BODY, "baked_tags": None, "baked_summary": None})
    assert r.status_code == 503
