"""Smoke test: emits one trace, one metric, and one log record via the OTEL SDK.

Run with the observability stack up:
    python scripts/smoke_test.py

Then check Grafana at http://localhost:3000 (OTEL Overview dashboard).
"""

from __future__ import annotations

import logging
import sys
import time

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider

from otel_common import init_otel

SERVICE_NAME = "otel-smoke"


def main() -> None:
    init_otel(SERVICE_NAME)

    tracer = trace.get_tracer(SERVICE_NAME)
    meter = metrics.get_meter(SERVICE_NAME)
    logger = logging.getLogger(SERVICE_NAME)

    counter = meter.create_counter(
        name="otel.smoke.counter",
        description="Incremented once per smoke test run",
        unit="1",
    )

    with tracer.start_as_current_span("smoke.operation") as span:
        span.set_attribute("smoke.run", "true")
        counter.add(1, {"smoke.run": "true"})
        logger.info("smoke_test_complete", extra={"event": "smoke_test_complete"})
        ctx = span.get_span_context()
        trace_id = format(ctx.trace_id, "032x")

    print(f"\nTrace ID : {trace_id}")
    print("Find it  : Grafana → Explore → Tempo → TraceQL → paste trace ID")
    print("Metric   : Grafana → OTEL Overview dashboard → Smoke Counter panel")
    print('Logs     : Grafana → Explore → Loki → {job="otel-smoke"}')
    print("\nFlushing exporters (allow ~2s for batches to drain)...")

    time.sleep(2)

    tp = trace.get_tracer_provider()
    mp = metrics.get_meter_provider()
    if isinstance(tp, TracerProvider):
        tp.force_flush()
    if isinstance(mp, MeterProvider):
        mp.force_flush()

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
