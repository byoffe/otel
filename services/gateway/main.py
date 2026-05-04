"""gateway-svc: orchestrates the transcript pipeline and exposes POST /jobs."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from pydantic import BaseModel

from otel_common import init_otel

SERVICE_NAME = "gateway-svc"
init_otel(SERVICE_NAME)
# Instrument all httpx.AsyncClient instances to inject W3C TraceContext headers
# into every outgoing request — this is what creates the distributed trace.
HTTPXClientInstrumentor().instrument()

app = FastAPI(title=SERVICE_NAME)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")

logger = logging.getLogger(SERVICE_NAME)
meter = metrics.get_meter(SERVICE_NAME)
_jobs_in_flight = meter.create_up_down_counter(
    name="pipeline.jobs_in_flight",
    description="Number of pipeline jobs currently in progress",
    unit="1",
)
_jobs_total = meter.create_counter(
    name="gateway.jobs_total",
    description="Total pipeline jobs completed, by status",
    unit="1",
)

_TRANSCRIPTION_URL = os.environ.get("TRANSCRIPTION_URL", "http://localhost:8001")
_DIARIZATION_URL = os.environ.get("DIARIZATION_URL", "http://localhost:8002")
_INDEXING_URL = os.environ.get("INDEXING_URL", "http://localhost:8003")
_STORAGE_URL = os.environ.get("STORAGE_URL", "http://localhost:8004")


class ConversationContent(BaseModel):
    """Pre-baked content for the /meeting skill.  When present, each downstream
    service uses these values instead of running its simulation."""

    text: str
    speakers: list[dict[str, Any]]
    tags: list[str]
    summary: str


class JobRequest(BaseModel):
    filename: str
    duration_seconds: float = 3600.0
    content: ConversationContent | None = None


class JobResponse(BaseModel):
    job_id: str
    transcript_id: str
    status: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/jobs", response_model=JobResponse)
async def create_job(body: JobRequest) -> JobResponse:
    job_id = str(uuid.uuid4())
    logger.info("job started", extra={"job_id": job_id, "audio_file": body.filename})

    baked = body.content
    _jobs_in_flight.add(1)
    try:
        return await _run_pipeline(job_id, body, baked)
    except HTTPException:
        _jobs_total.add(1, {"status": "error"})
        raise
    finally:
        _jobs_in_flight.add(-1)


async def _run_pipeline(
    job_id: str, body: JobRequest, baked: ConversationContent | None
) -> JobResponse:
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1 — transcribe
        transcribe_payload: dict[str, Any] = {
            "filename": body.filename,
            "duration_seconds": body.duration_seconds,
        }
        if baked:
            transcribe_payload["baked_text"] = baked.text
        r = await client.post(f"{_TRANSCRIPTION_URL}/transcribe", json=transcribe_payload)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"transcription failed: {r.text}")
        transcription = r.json()

        # 2 — diarize
        diarize_payload: dict[str, Any] = {
            "transcript_id": transcription["transcript_id"],
            "text": transcription["text"],
        }
        if baked:
            diarize_payload["baked_speakers"] = baked.speakers
        r = await client.post(f"{_DIARIZATION_URL}/diarize", json=diarize_payload)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"diarization failed: {r.text}")
        diarization = r.json()

        # 3 — index
        index_payload: dict[str, Any] = {
            "transcript_id": transcription["transcript_id"],
            "text": transcription["text"],
            "speakers": diarization["speakers"],
        }
        if baked:
            index_payload["baked_tags"] = baked.tags
            index_payload["baked_summary"] = baked.summary
        r = await client.post(f"{_INDEXING_URL}/index", json=index_payload)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"indexing failed: {r.text}")
        indexing = r.json()

        # 4 — store
        r = await client.post(
            f"{_STORAGE_URL}/transcripts",
            json={
                "transcript_id": transcription["transcript_id"],
                "filename": body.filename,
                "text": transcription["text"],
                "speakers": diarization["speakers"],
                "tags": indexing["tags"],
                "summary": indexing["summary"],
            },
        )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"storage failed: {r.text}")
        stored = r.json()

    transcript_id: str = stored["id"]
    logger.info(
        "job complete",
        extra={"job_id": job_id, "transcript_id": transcript_id},
    )
    _jobs_total.add(1, {"status": "success"})
    return JobResponse(job_id=job_id, transcript_id=transcript_id, status="complete")
