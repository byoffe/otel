"""Tests for the storage service — span attributes and metric emission."""

import pytest
from helpers import emitted_metric_names, find_span
from fastapi.testclient import TestClient

from services.storage.main import _store, app

client = TestClient(app)

TRANSCRIPT = {
    "transcript_id": "t-001",
    "filename": "standup.mp3",
    "text": "Alice: good morning\nBob: morning all",
    "speakers": [{"name": "Alice", "word_count": 2}, {"name": "Bob", "word_count": 2}],
    "tags": ["standup"],
    "summary": "Morning standup",
}


@pytest.fixture(autouse=True)
def clear_store():
    _store.clear()
    yield
    _store.clear()


# --- span assertions -------------------------------------------------------


def test_span_records_transcript_id(span_exporter):
    client.post("/transcripts", json=TRANSCRIPT)
    span = find_span(span_exporter, **{"storage.transcript_id": "t-001"})
    assert span is not None, "expected a span with storage.transcript_id=t-001"


def test_span_present_for_get(span_exporter):
    client.post("/transcripts", json=TRANSCRIPT)
    span_exporter.clear()
    client.get("/transcripts/t-001")
    assert len(span_exporter.get_finished_spans()) > 0


# --- metric assertions ------------------------------------------------------


def test_stored_counter_emitted(metric_reader):
    client.post("/transcripts", json=TRANSCRIPT)
    assert "storage.transcripts_stored_total" in emitted_metric_names(metric_reader)


def test_counter_increments_per_request(metric_reader):
    for i in range(3):
        client.post("/transcripts", json={**TRANSCRIPT, "transcript_id": f"t-{i:03d}"})
    data = metric_reader.get_metrics_data()
    metric = next(
        m
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "storage.transcripts_stored_total"
    )
    total = sum(dp.value for dp in metric.data.data_points)
    assert total >= 3


# --- interaction assertions -------------------------------------------------


def test_store_uses_provided_id():
    r = client.post("/transcripts", json=TRANSCRIPT)
    assert r.status_code == 200
    assert r.json()["id"] == "t-001"


def test_get_returns_full_record():
    client.post("/transcripts", json=TRANSCRIPT)
    r = client.get("/transcripts/t-001")
    assert r.status_code == 200
    assert r.json()["filename"] == "standup.mp3"


def test_get_missing_returns_404():
    r = client.get("/transcripts/does-not-exist")
    assert r.status_code == 404


def test_list_excludes_full_text():
    client.post("/transcripts", json=TRANSCRIPT)
    items = client.get("/transcripts").json()
    assert len(items) == 1
    assert "text" not in items[0]
