"""pipeline-analyst MCP server — queries Tempo to diagnose pipeline performance."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastmcp import FastMCP
from opentelemetry import trace as otel_trace

from otel_common import init_otel

SERVICE_NAME = "mcp-server"
init_otel(SERVICE_NAME)

TEMPO_URL = os.environ.get("TEMPO_URL", "http://localhost:3200")

mcp = FastMCP("pipeline-analyst")
tracer = otel_trace.get_tracer(SERVICE_NAME)


def _now_s() -> int:
    return int(time.time())


def _ago_s(seconds: int = 3600) -> int:
    return int(time.time() - seconds)


@mcp.tool()
async def list_recent_jobs(limit: int = 20) -> list[dict[str, Any]]:
    """List recent POST /jobs pipeline runs with trace ID, duration, and timestamp.

    Returns the last `limit` pipeline executions from the past hour, ordered
    newest-first. Use this to get an overview of recent activity before drilling
    into a specific trace with get_trace_breakdown.
    """
    with tracer.start_as_current_span("mcp.list_recent_jobs") as span:
        span.set_attribute("mcp.tool", "list_recent_jobs")
        span.set_attribute("mcp.limit", limit)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TEMPO_URL}/api/search",
                params={
                    "q": '{rootName="POST /jobs"}',
                    "limit": limit,
                    "start": _ago_s(3600),
                    "end": _now_s(),
                },
                timeout=10,
            )
            resp.raise_for_status()
        traces = resp.json().get("traces", [])
        span.set_attribute("mcp.result_count", len(traces))
        return [
            {
                "trace_id": t["traceID"],
                "duration_ms": t.get("durationMs", 0),
                "started_at_ns": t.get("startTimeUnixNano", ""),
                "root_service": t.get("rootServiceName", ""),
            }
            for t in traces
        ]


@mcp.tool()
async def get_trace_breakdown(trace_id: str) -> dict[str, Any]:
    """Return per-service timing for one pipeline trace.

    Fetches the full span tree from Tempo and returns the wall-clock time spent
    in each service (SERVER spans only). Also computes gateway overhead as the
    difference between the total job time and the sum of downstream service times.

    Example return:
      {
        "trace_id": "abc123",
        "total_ms": 1850,
        "services": {
          "transcription-svc": 620,
          "diarization-svc": 440,
          "indexing-svc": 770,
          "storage-svc": 5,
          "gateway-overhead-ms": 15
        }
      }
    """
    with tracer.start_as_current_span("mcp.get_trace_breakdown") as span:
        span.set_attribute("mcp.tool", "get_trace_breakdown")
        span.set_attribute("mcp.trace_id", trace_id)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TEMPO_URL}/api/traces/{trace_id}",
                timeout=10,
            )
            resp.raise_for_status()
        data = resp.json()

        # SERVER span duration per service = actual request-handler wall-clock time.
        # CLIENT spans (gateway's outgoing httpx calls) are excluded to avoid double-counting.
        server_spans: dict[str, int] = {}
        gateway_total = 0

        for batch in data.get("batches", []):
            svc = next(
                (
                    list(a["value"].values())[0]
                    for a in batch.get("resource", {}).get("attributes", [])
                    if a.get("key") == "service.name"
                ),
                "unknown",
            )
            for scope in batch.get("scopeSpans", []):
                for s in scope.get("spans", []):
                    if s.get("kind") != "SPAN_KIND_SERVER":
                        continue
                    start = int(s.get("startTimeUnixNano", 0))
                    end = int(s.get("endTimeUnixNano", 0))
                    if start and end:
                        dur_ms = (end - start) // 1_000_000
                        if svc == "gateway-svc":
                            gateway_total = dur_ms
                        else:
                            server_spans[svc] = dur_ms

        downstream_total = sum(server_spans.values())
        gateway_overhead = max(0, gateway_total - downstream_total)

        return {
            "trace_id": trace_id,
            "total_ms": gateway_total,
            "services": {**server_spans, "gateway-overhead-ms": gateway_overhead},
        }


@mcp.tool()
async def find_slow_jobs(threshold_ms: int = 3000) -> list[dict[str, Any]]:
    """Find pipeline jobs whose end-to-end duration exceeded threshold_ms milliseconds.

    Uses Tempo TraceQL to filter efficiently server-side. Searches the past hour.
    Returns trace IDs and durations — use get_trace_breakdown on any result to
    pinpoint which service was responsible for the slowness.
    """
    with tracer.start_as_current_span("mcp.find_slow_jobs") as span:
        span.set_attribute("mcp.tool", "find_slow_jobs")
        span.set_attribute("mcp.threshold_ms", threshold_ms)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TEMPO_URL}/api/search",
                params={
                    "q": f'{{rootName="POST /jobs" && duration > {threshold_ms}ms}}',
                    "limit": 20,
                    "start": _ago_s(3600),
                    "end": _now_s(),
                },
                timeout=10,
            )
            resp.raise_for_status()
        traces = resp.json().get("traces", [])
        span.set_attribute("mcp.result_count", len(traces))
        return [
            {
                "trace_id": t["traceID"],
                "duration_ms": t.get("durationMs", 0),
            }
            for t in traces
        ]


@mcp.tool()
async def find_error_jobs() -> list[dict[str, Any]]:
    """Find pipeline jobs that contained error spans (HTTP 5xx or OTEL status=ERROR).

    Use this to identify failed runs. The indexing-svc has a configurable error
    rate (SIM_ERROR_RATE env var) that can be increased to generate errors for demo.
    Returns trace IDs — use get_trace_breakdown to see which service errored.
    """
    with tracer.start_as_current_span("mcp.find_error_jobs") as span:
        span.set_attribute("mcp.tool", "find_error_jobs")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TEMPO_URL}/api/search",
                params={
                    "q": '{rootName="POST /jobs" && status=error}',
                    "limit": 20,
                    "start": _ago_s(3600),
                    "end": _now_s(),
                },
                timeout=10,
            )
            resp.raise_for_status()
        traces = resp.json().get("traces", [])
        span.set_attribute("mcp.result_count", len(traces))
        return [
            {
                "trace_id": t["traceID"],
                "duration_ms": t.get("durationMs", 0),
            }
            for t in traces
        ]
