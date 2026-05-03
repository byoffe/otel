"""Tests for the transcription service — span attributes and metric emission."""

from fastapi.testclient import TestClient
from helpers import emitted_metric_names, find_span

from services.transcription.main import app

client = TestClient(app)

BAKED = {
    "filename": "meeting.mp3",
    "duration_seconds": 60.0,
    "baked_text": "hello world this is a test transcript",
}


# --- span assertions -------------------------------------------------------


def test_span_records_word_count(span_exporter):
    client.post("/transcribe", json=BAKED)
    span = find_span(span_exporter, **{"transcript.word_count": 7})
    assert span is not None, "expected span with transcript.word_count=7"


def test_span_word_count_matches_baked_text(span_exporter):
    payload = {**BAKED, "baked_text": "one two three"}
    client.post("/transcribe", json=payload)
    span = find_span(span_exporter, **{"transcript.word_count": 3})
    assert span is not None


# --- metric assertions ------------------------------------------------------


def test_duration_histogram_emitted(metric_reader):
    client.post("/transcribe", json=BAKED)
    assert "transcription.duration_seconds" in emitted_metric_names(metric_reader)


def test_histogram_records_one_observation_per_request(metric_reader):
    client.post("/transcribe", json=BAKED)
    client.post("/transcribe", json=BAKED)
    data = metric_reader.get_metrics_data()
    metric = next(
        m
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "transcription.duration_seconds"
    )
    total_count = sum(dp.count for dp in metric.data.data_points)
    assert total_count >= 2


# --- interaction assertions -------------------------------------------------


def test_baked_text_returned_verbatim():
    r = client.post("/transcribe", json=BAKED)
    assert r.status_code == 200
    assert r.json()["text"] == BAKED["baked_text"]


def test_response_contains_transcript_id():
    r = client.post("/transcribe", json=BAKED)
    tid = r.json().get("transcript_id", "")
    assert len(tid) == 36  # UUID
