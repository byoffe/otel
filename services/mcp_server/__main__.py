"""Entry point for pipeline-analyst MCP server.

stdio (default): Claude Code spawns this as a subprocess via .claude/mcp.json.
sse:             Docker Compose runs it as a persistent SSE service on port 8005.

OTEL providers are force-flushed on exit so spans reach Tempo even in the
short-lived stdio process (BatchSpanProcessor won't drain on its own).
"""

from __future__ import annotations

import os

from opentelemetry import metrics, trace

from . import mcp


def _flush_providers() -> None:
    tp = trace.get_tracer_provider()
    if hasattr(tp, "force_flush"):
        tp.force_flush(timeout_millis=5000)  # type: ignore[attr-defined]
    mp = metrics.get_meter_provider()
    if hasattr(mp, "force_flush"):
        mp.force_flush(timeout_millis=5000)  # type: ignore[attr-defined]


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    try:
        if transport == "sse":
            port = int(os.environ.get("MCP_PORT", "8005"))
            mcp.run(transport="sse", host="0.0.0.0", port=port)
        else:
            mcp.run()
    finally:
        _flush_providers()
