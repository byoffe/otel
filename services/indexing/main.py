"""indexing-svc: simulates LLM-based tagging and summarisation with configurable error rate."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any

from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from otel_common import init_otel

SERVICE_NAME = "indexing-svc"
init_otel(SERVICE_NAME)

app = FastAPI(title=SERVICE_NAME)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")

logger = logging.getLogger(SERVICE_NAME)
meter = metrics.get_meter(SERVICE_NAME)
_token_histogram = meter.create_histogram(
    name="indexing.llm_tokens_used",
    description="Simulated LLM token usage per indexing request",
    unit="tokens",
)
_error_counter = meter.create_counter(
    name="indexing.errors_total",
    description="Total simulated LLM failures",
    unit="1",
)

_DELAY_MIN = float(os.environ.get("SIM_DELAY_MIN", "0.4"))
_DELAY_MAX = float(os.environ.get("SIM_DELAY_MAX", "1.2"))
_ERROR_RATE = float(os.environ.get("SIM_ERROR_RATE", "0.0"))
_MODEL = "gpt-simulation-v1"

_TAG_POOL = [
    "quarterly-review",
    "budget",
    "product-roadmap",
    "hiring",
    "customer-feedback",
    "engineering",
    "sales",
    "marketing",
    "strategy",
    "retrospective",
    "planning",
    "incident-review",
    "design-review",
    "all-hands",
]
_SUMMARIES = [
    "Team reviewed quarterly targets; key action items assigned to leads.",
    "Product roadmap discussed with focus on upcoming customer-facing releases.",
    "Sprint retrospective identified three process improvements for next cycle.",
    "Customer feedback themes synthesised; follow-up sessions scheduled.",
    "Budget allocation reviewed; headcount plan approved for next half.",
]


class IndexRequest(BaseModel):
    transcript_id: str
    text: str
    speakers: list[dict[str, Any]]
    baked_tags: list[str] | None = None
    baked_summary: str | None = None


class IndexResponse(BaseModel):
    transcript_id: str
    tags: list[str]
    summary: str
    model: str
    tokens_used: int


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/index", response_model=IndexResponse)
async def index(body: IndexRequest) -> IndexResponse:
    await asyncio.sleep(random.uniform(_DELAY_MIN, _DELAY_MAX))

    if body.baked_tags is not None and body.baked_summary is not None:
        tags = body.baked_tags
        summary = body.baked_summary
        tokens_used = len(body.text.split()) * 2  # rough estimate: ~2 tokens per word
    else:
        if random.random() < _ERROR_RATE:
            _error_counter.add(1)
            span = trace.get_current_span()
            span.set_status(trace.StatusCode.ERROR, "simulated LLM timeout")
            logger.error(
                "LLM call failed (simulated)",
                extra={"transcript_id": body.transcript_id},
            )
            raise HTTPException(status_code=503, detail="LLM service unavailable (simulated)")

        tokens_used = random.randint(800, 4000)
        tags = random.sample(_TAG_POOL, random.randint(2, 5))
        summary = random.choice(_SUMMARIES)

    _token_histogram.record(tokens_used)
    span = trace.get_current_span()
    span.set_attribute("indexing.model", _MODEL)
    span.set_attribute("indexing.tokens_used", tokens_used)
    logger.info(
        "indexing complete",
        extra={"transcript_id": body.transcript_id, "tags": ",".join(tags)},
    )
    return IndexResponse(
        transcript_id=body.transcript_id,
        tags=tags,
        summary=summary,
        model=_MODEL,
        tokens_used=tokens_used,
    )
