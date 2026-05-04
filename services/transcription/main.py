"""transcription-svc: simulates ASR (audio → text) with configurable delay."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
import uuid

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from otel_common import init_otel

SERVICE_NAME = "transcription-svc"
init_otel(SERVICE_NAME)

app = FastAPI(title=SERVICE_NAME)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")

logger = logging.getLogger(SERVICE_NAME)
meter = metrics.get_meter(SERVICE_NAME)
_duration_histogram = meter.create_histogram(
    name="transcription.duration_seconds",
    description="Simulated ASR processing time per request",
    unit="s",
)
_word_count_histogram = meter.create_histogram(
    name="transcription.word_count",
    description="Distribution of transcript word counts",
    unit="words",
)

_DELAY_MIN = float(os.environ.get("SIM_DELAY_MIN", "0.3"))
_DELAY_MAX = float(os.environ.get("SIM_DELAY_MAX", "0.9"))

_FILLER_WORDS = [
    "the",
    "meeting",
    "commenced",
    "agenda",
    "discussed",
    "quarter",
    "revenue",
    "team",
    "action",
    "items",
    "following",
    "stakeholders",
    "review",
    "roadmap",
    "budget",
    "allocated",
    "resources",
    "timeline",
    "delivery",
    "milestone",
]


class TranscribeRequest(BaseModel):
    filename: str
    duration_seconds: float
    baked_text: str | None = None


class TranscribeResponse(BaseModel):
    transcript_id: str
    text: str
    word_count: int


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(body: TranscribeRequest) -> TranscribeResponse:
    t0 = time.perf_counter()
    await asyncio.sleep(random.uniform(_DELAY_MIN, _DELAY_MAX))

    if body.baked_text is not None:
        text = body.baked_text
        word_count = len(text.split())
    else:
        word_count = int(body.duration_seconds * random.uniform(110, 150))
        text = " ".join(random.choices(_FILLER_WORDS, k=min(word_count, 300)))
    transcript_id = str(uuid.uuid4())
    duration = time.perf_counter() - t0

    _duration_histogram.record(duration)
    _word_count_histogram.record(word_count)
    trace.get_current_span().set_attribute("transcript.word_count", word_count)
    logger.info(
        "transcription complete",
        extra={"transcript_id": transcript_id, "word_count": word_count},
    )
    return TranscribeResponse(transcript_id=transcript_id, text=text, word_count=word_count)
