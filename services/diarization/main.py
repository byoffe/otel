"""diarization-svc: simulates speaker attribution with configurable delay."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from otel_common import init_otel

SERVICE_NAME = "diarization-svc"
init_otel(SERVICE_NAME)

app = FastAPI(title=SERVICE_NAME)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")

logger = logging.getLogger(SERVICE_NAME)
meter = metrics.get_meter(SERVICE_NAME)
_segments_counter = meter.create_counter(
    name="diarization.segments_total",
    description="Total speaker segments identified across all requests",
    unit="1",
)

_DELAY_MIN = float(os.environ.get("SIM_DELAY_MIN", "0.2"))
_DELAY_MAX = float(os.environ.get("SIM_DELAY_MAX", "0.6"))
_SPEAKER_NAMES = ["Alice", "Bob", "Carol", "David", "Eve"]


class DiarizeRequest(BaseModel):
    transcript_id: str
    text: str
    baked_speakers: list[dict[str, Any]] | None = None


class Speaker(BaseModel):
    name: str
    word_count: int


class DiarizeResponse(BaseModel):
    transcript_id: str
    speakers: list[Speaker]
    segment_count: int


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/diarize", response_model=DiarizeResponse)
async def diarize(body: DiarizeRequest) -> DiarizeResponse:
    await asyncio.sleep(random.uniform(_DELAY_MIN, _DELAY_MAX))

    if body.baked_speakers is not None:
        speakers = [Speaker(**s) for s in body.baked_speakers]
        speaker_count = len(speakers)
        # count actual speaker turns: lines that start with "Name:"
        speaker_names = {s["name"] for s in body.baked_speakers}
        segment_count = (
            sum(
                1
                for line in body.text.splitlines()
                if any(line.startswith(name + ":") for name in speaker_names)
            )
            or speaker_count * 5
        )
    else:
        speaker_count = random.randint(2, min(4, len(_SPEAKER_NAMES)))
        names = random.sample(_SPEAKER_NAMES, speaker_count)
        total_words = max(len(body.text.split()), 1)
        shares = [random.random() for _ in names]
        total = sum(shares)
        speakers = [
            Speaker(name=n, word_count=int(total_words * s / total)) for n, s in zip(names, shares)
        ]
        segment_count = random.randint(speaker_count * 3, speaker_count * 8)

    _segments_counter.add(segment_count)
    trace.get_current_span().set_attribute("diarization.speaker_count", speaker_count)
    logger.info(
        "diarization complete",
        extra={"transcript_id": body.transcript_id, "speaker_count": speaker_count},
    )
    return DiarizeResponse(
        transcript_id=body.transcript_id,
        speakers=speakers,
        segment_count=segment_count,
    )
