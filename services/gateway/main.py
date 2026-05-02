"""gateway-svc: orchestrates the transcript pipeline and exposes POST /jobs."""

from __future__ import annotations

import logging
import os
import uuid

import httpx
from fastapi import FastAPI, HTTPException
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

_TRANSCRIPTION_URL = os.environ.get("TRANSCRIPTION_URL", "http://localhost:8001")
_DIARIZATION_URL = os.environ.get("DIARIZATION_URL", "http://localhost:8002")
_INDEXING_URL = os.environ.get("INDEXING_URL", "http://localhost:8003")
_STORAGE_URL = os.environ.get("STORAGE_URL", "http://localhost:8004")


class JobRequest(BaseModel):
    filename: str
    duration_seconds: float = 3600.0


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

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1 — transcribe
        r = await client.post(
            f"{_TRANSCRIPTION_URL}/transcribe",
            json={"filename": body.filename, "duration_seconds": body.duration_seconds},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"transcription failed: {r.text}")
        transcription = r.json()

        # 2 — diarize
        r = await client.post(
            f"{_DIARIZATION_URL}/diarize",
            json={"transcript_id": transcription["transcript_id"], "text": transcription["text"]},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"diarization failed: {r.text}")
        diarization = r.json()

        # 3 — index
        r = await client.post(
            f"{_INDEXING_URL}/index",
            json={
                "transcript_id": transcription["transcript_id"],
                "text": transcription["text"],
                "speakers": diarization["speakers"],
            },
        )
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
    return JobResponse(job_id=job_id, transcript_id=transcript_id, status="complete")
