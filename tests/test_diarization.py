"""Tests for the diarization service — span attributes and metric emission."""

from helpers import emitted_metric_names, find_span
from fastapi.testclient import TestClient

from services.diarization.main import app

client = TestClient(app)

BAKED_BODY = {
    "transcript_id": "t-diar-001",
    "text": "Alice: good morning everyone\nBob: morning Alice\nAlice: let us begin",
    "baked_speakers": [
        {"name": "Alice", "word_count": 7},
        {"name": "Bob", "word_count": 2},
    ],
}


# --- span assertions -------------------------------------------------------


def test_span_records_speaker_count(span_exporter):
    client.post("/diarize", json=BAKED_BODY)
    span = find_span(span_exporter, **{"diarization.speaker_count": 2})
    assert span is not None, "expected span with diarization.speaker_count=2"


def test_span_speaker_count_reflects_baked_speakers(span_exporter):
    body = {
        **BAKED_BODY,
        "baked_speakers": [
            {"name": "Alice", "word_count": 5},
            {"name": "Bob", "word_count": 3},
            {"name": "Carol", "word_count": 2},
        ],
    }
    client.post("/diarize", json=body)
    span = find_span(span_exporter, **{"diarization.speaker_count": 3})
    assert span is not None


# --- metric assertions ------------------------------------------------------


def test_segments_counter_emitted(metric_reader):
    client.post("/diarize", json=BAKED_BODY)
    assert "diarization.segments_total" in emitted_metric_names(metric_reader)


def test_segments_counter_reflects_turn_count(metric_reader):
    # Text has 3 lines starting with a speaker name → 3 segments
    client.post("/diarize", json=BAKED_BODY)
    data = metric_reader.get_metrics_data()
    metric = next(
        m
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "diarization.segments_total"
    )
    total = sum(dp.value for dp in metric.data.data_points)
    assert total >= 3


# --- interaction assertions -------------------------------------------------


def test_baked_speakers_returned(span_exporter):
    r = client.post("/diarize", json=BAKED_BODY)
    assert r.status_code == 200
    names = {s["name"] for s in r.json()["speakers"]}
    assert names == {"Alice", "Bob"}


def test_segment_count_counts_speaker_turns():
    r = client.post("/diarize", json=BAKED_BODY)
    # 3 lines starting with a known speaker name
    assert r.json()["segment_count"] == 3
