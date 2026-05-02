# OTEL Conference Transcript Pipeline

A simulated ML pipeline for learning OpenTelemetry (traces, metrics, logs), MCP
(Model Context Protocol), and AI agent skills. The pipeline processes conference
audio recordings through transcription, speaker diarization, LLM indexing, and
storage — all simulated, all fully instrumented.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Compose v2)
- Python 3.12+

## Quick start

**1. Start the observability stack**

```bash
docker compose up -d
```

Wait ~20s for all services to become healthy. Check with:

```bash
docker compose ps
```

**2. Set up the Python environment**

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt
```

**3. Run the smoke test**

```bash
python scripts/smoke_test.py
```

The script prints a Trace ID and instructions for finding each signal in Grafana.

## Ports

| Service          | Port  | Purpose                        |
|------------------|-------|--------------------------------|
| Grafana          | 3000  | Visualization UI               |
| OTLP gRPC        | 4317  | App telemetry ingest (gRPC)    |
| OTLP HTTP        | 4318  | App telemetry ingest (HTTP)    |
| Tempo            | 3200  | Trace search API               |
| Prometheus       | 9090  | Metrics query UI               |
| Loki             | 3100  | Log query API                  |
| Collector metrics| 8889  | Prometheus scrape endpoint     |

Grafana credentials: `admin` / `admin`

## Where to find each signal in Grafana

Open **http://localhost:3000** then navigate to:

| Signal  | Where                                                                 |
|---------|-----------------------------------------------------------------------|
| Traces  | Dashboards → OTEL Overview → "Recent Traces" panel, or Explore → Tempo → TraceQL: `{}` |
| Metrics | Dashboards → OTEL Overview → "Smoke Counter" panel, or Explore → Prometheus: `otel_smoke_counter_total` |
| Logs    | Dashboards → OTEL Overview → "Recent Logs" panel, or Explore → Loki: `{job="otel-smoke"}` |

**Trace correlation:** In any log line, if a `trace_id` field is present, a
"View Trace in Tempo" link appears — clicking it jumps directly to that trace.

## Architecture

```
Your app / script
  └── OTEL SDK (otel_common.init_otel)
        └── OTLP/gRPC → otel-collector:4317
                          ├── traces  → Tempo:3200
                          ├── metrics → Prometheus:9090  (via scrape)
                          └── logs    → Loki:3100
                                          ↕
                                       Grafana:3000
```

## Project structure

```
otel_common/          Shared OTEL SDK init (used by all services and scripts)
scripts/              Standalone scripts (smoke test, seed data)
services/             Microservices (added in Story 2)
  gateway/
  transcription/
  diarization/
  indexing/
  storage/
mcp_server/           FastMCP server for Claude integration (Story 3)
otel-collector/       OTEL Collector config
tempo/                Tempo config
prometheus/           Prometheus config
loki/                 Loki config
grafana/              Grafana provisioning and dashboards
.github/workflows/    CI (lint, format, type check)
spec/                 Project spec (requirements, design, tasks)
```

## Development

Run lint, format check, and type check locally:

```bash
ruff check .
ruff format --check .
pyright
```

Auto-fix formatting:

```bash
ruff format .
```

Stop the stack:

```bash
docker compose down
```

Destroy all data volumes (full reset):

```bash
docker compose down -v
```
