"""storage-svc: persists transcripts in memory; exposes list/get REST endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from otel_common import init_otel

SERVICE_NAME = "storage-svc"
init_otel(SERVICE_NAME)

app = FastAPI(title=SERVICE_NAME)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")

logger = logging.getLogger(SERVICE_NAME)
meter = metrics.get_meter(SERVICE_NAME)
_stored_counter = meter.create_counter(
    name="storage.transcripts_stored_total",
    description="Total number of transcripts stored",
    unit="1",
)

_store: dict[str, dict[str, Any]] = {}


class TranscriptIn(BaseModel):
    transcript_id: str
    filename: str
    text: str
    speakers: list[dict[str, Any]]
    tags: list[str]
    summary: str


class TranscriptStored(BaseModel):
    id: str
    created_at: str


class TranscriptSummary(BaseModel):
    id: str
    filename: str
    tags: list[str]
    created_at: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/transcripts", response_model=TranscriptStored)
async def store_transcript(body: TranscriptIn) -> TranscriptStored:
    record_id = body.transcript_id or str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    _store[record_id] = {
        "id": record_id,
        "filename": body.filename,
        "text": body.text,
        "speakers": body.speakers,
        "tags": body.tags,
        "summary": body.summary,
        "created_at": created_at,
    }
    _stored_counter.add(1)
    trace.get_current_span().set_attribute("storage.transcript_id", record_id)
    logger.info("transcript stored", extra={"transcript_id": record_id})
    return TranscriptStored(id=record_id, created_at=created_at)


@app.get("/transcripts", response_model=list[TranscriptSummary])
async def list_transcripts() -> list[TranscriptSummary]:
    return [
        TranscriptSummary(
            id=v["id"],
            filename=v["filename"],
            tags=v["tags"],
            created_at=v["created_at"],
        )
        for v in _store.values()
    ]


@app.get("/transcripts/{transcript_id}")
async def get_transcript(transcript_id: str) -> dict[str, Any]:
    if transcript_id not in _store:
        raise HTTPException(status_code=404, detail="transcript not found")
    return _store[transcript_id]
