"""Tests for the gateway service — span presence and downstream interactions."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from services.gateway.main import app

client = TestClient(app)

JOB_REQUEST = {
    "filename": "board-meeting.mp3",
    "duration_seconds": 3600.0,
    "content": {
        "text": "Alice: welcome everyone\nBob: thanks Alice",
        "speakers": [{"name": "Alice", "word_count": 2}, {"name": "Bob", "word_count": 2}],
        "tags": ["board", "strategy"],
        "summary": "Board meeting summary",
    },
}


def _mock_pipeline():
    """Return an AsyncMock httpx client that walks the happy-path responses."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    def _resp(status: int, body: dict) -> MagicMock:
        r = MagicMock()
        r.status_code = status
        r.json.return_value = body
        r.text = str(body)
        return r

    mock_client.post.side_effect = [
        _resp(200, {"transcript_id": "t-gw-001", "text": "Alice: welcome", "word_count": 3}),
        _resp(
            200,
            {
                "transcript_id": "t-gw-001",
                "speakers": [{"name": "Alice", "word_count": 3}],
                "segment_count": 1,
            },
        ),
        _resp(
            200,
            {
                "transcript_id": "t-gw-001",
                "tags": ["board"],
                "summary": "s",
                "model": "m",
                "tokens_used": 6,
            },
        ),
        _resp(200, {"id": "t-gw-001", "created_at": "2026-01-01T00:00:00Z"}),
    ]
    return mock_client


# --- span assertions -------------------------------------------------------


def test_span_created_for_job_request(span_exporter):
    with patch("httpx.AsyncClient", return_value=_mock_pipeline()):
        client.post("/jobs", json=JOB_REQUEST)
    assert len(span_exporter.get_finished_spans()) > 0


# --- interaction assertions -------------------------------------------------


def test_calls_all_four_downstream_services():
    mock = _mock_pipeline()
    with patch("httpx.AsyncClient", return_value=mock):
        r = client.post("/jobs", json=JOB_REQUEST)
    assert r.status_code == 200
    assert mock.post.call_count == 4


def test_calls_services_in_pipeline_order():
    mock = _mock_pipeline()
    with patch("httpx.AsyncClient", return_value=mock):
        client.post("/jobs", json=JOB_REQUEST)
    urls = [str(call.args[0]) for call in mock.post.call_args_list]
    assert urls[0].endswith("/transcribe")
    assert urls[1].endswith("/diarize")
    assert urls[2].endswith("/index")
    assert urls[3].endswith("/transcripts")


def test_response_contains_transcript_id_and_status():
    with patch("httpx.AsyncClient", return_value=_mock_pipeline()):
        r = client.post("/jobs", json=JOB_REQUEST)
    data = r.json()
    assert data["transcript_id"] == "t-gw-001"
    assert data["status"] == "complete"


def test_transcription_failure_returns_502():
    mock = _mock_pipeline()
    mock.post.side_effect = None
    mock.post.return_value = MagicMock(status_code=500, text="internal error")
    with patch("httpx.AsyncClient", return_value=mock):
        r = client.post("/jobs", json=JOB_REQUEST)
    assert r.status_code == 502


def test_storage_failure_returns_502():
    mock = _mock_pipeline()
    responses = list(mock.post.side_effect)
    responses[-1] = MagicMock(status_code=500, text="storage down")
    mock.post.side_effect = responses
    with patch("httpx.AsyncClient", return_value=mock):
        r = client.post("/jobs", json=JOB_REQUEST)
    assert r.status_code == 502
