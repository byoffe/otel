# Design: OTEL Conference Transcript Pipeline

## Commit 1 — Observability Infrastructure + Project Scaffold

### Scope

Addresses all Story 1 acceptance criteria:
- Docker Compose stack: OTEL Collector, Tempo, Prometheus, Loki, Grafana
- Grafana datasources and starter dashboard provisioned automatically
- Python project scaffold: `pyproject.toml`, `venv`, `ruff`, `pyright`
- GitHub Actions CI: lint, format, type check
- `scripts/smoke_test.py`: emits one trace, one metric, one log via OTEL SDK
- `README.md` for getting started

### Approach

Stand up the full observability backend first so every story that follows has
somewhere to send signals. The OTEL Collector is the central hub: all application
code (services, smoke test, MCP server) emits to the Collector via OTLP (gRPC on
port 4317); the Collector fans out to Tempo (traces), Prometheus (metrics via
remote-write or scrape), and Loki (logs). This means application code never needs
to know which backend it's talking to — a realistic architecture that also isolates
the demo from backend changes.

Grafana is configured entirely through provisioning files mounted at startup
(no UI clicks required), which keeps the stack reproducible.

The Python scaffold is intentionally minimal for this commit: a `pyproject.toml`
at the repo root (dev tooling config only — `ruff`, `pyright` settings and deps),
a `requirements-dev.txt` aggregating all deps for local dev and CI, a shared
`otel_common/` package for OTEL SDK initialization, and `scripts/smoke_test.py`.
Services will be added in Commit 2, each with their own `requirements.txt` for
Docker builds.

### Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| OTEL transport | OTLP/gRPC (port 4317) | Standard; supported by all OTEL Collector exporters and the Python SDK |
| Metrics pipeline | Collector → Prometheus remote-write | Avoids running a separate push-gateway; Collector handles the translation |
| Log pipeline | Collector → Loki via `loki` exporter | Direct path; no Promtail needed for application logs |
| Grafana provisioning | Mounted YAML files in `grafana/provisioning/` | Zero manual setup; stack is fully reproducible with `docker compose up` |
| Python toolchain | `venv` + `pip`, `ruff`, `pyright` | Matches existing project setup; `ruff` is fast and covers both lint and format |
| Dependency structure | Root `pyproject.toml` for tooling; per-service `requirements.txt` for Docker; `requirements-dev.txt` for local dev | Services are independently deployable; local dev stays simple with one venv |
| Smoke test signals | One `Counter`, one `Span`, one log record | Minimal but exercises all three pipelines end-to-end |
| OTEL SDK init | Shared `otel_common/` package | Every service and the smoke test will use the same init pattern; teaches the setup once |

### File and Component Changes

| File / Path | Purpose |
|---|---|
| `docker-compose.yml` | Defines: otel-collector, tempo, prometheus, loki, grafana |
| `otel-collector/config.yaml` | Collector pipelines: receivers (otlp), exporters (tempo, prometheus, loki) |
| `tempo/tempo.yaml` | Tempo config: storage backend (local), OTLP receiver enabled |
| `prometheus/prometheus.yml` | Scrape config for collector metrics endpoint |
| `loki/loki-config.yaml` | Loki config: local filesystem storage, default retention |
| `grafana/provisioning/datasources/datasources.yaml` | Wires Tempo, Prometheus, Loki into Grafana |
| `grafana/provisioning/dashboards/dashboards.yaml` | Points Grafana at the dashboard JSON directory |
| `grafana/dashboards/otel-overview.json` | Starter dashboard: trace search, metric panel, log panel |
| `pyproject.toml` | Tool config only: `[tool.ruff]`, `[tool.pyright]`, dev dep declarations |
| `requirements-dev.txt` | Union of all deps for local dev and CI (`pip install -r requirements-dev.txt`) |
| `.github/workflows/ci.yml` | Lint, format-check, pyright on push/PR to main |
| `otel_common/__init__.py` | `init_otel(service_name)` — configures TracerProvider, MeterProvider, LoggerProvider with OTLP exporters |
| `scripts/smoke_test.py` | Emits one span, one counter increment, one log record; prints trace ID |
| `README.md` | Prerequisites, `docker compose up`, smoke test instructions, Grafana navigation guide |
| `.gitignore` | Python, venv, IDE, OS artifacts |

### OTEL Collector Pipeline (summary)

```
App (OTLP/gRPC 4317)
  └─ otel-collector
       ├─ traces  → Tempo  (OTLP/gRPC 4317 internal)
       ├─ metrics → Prometheus (remote-write or scrape /metrics)
       └─ logs    → Loki  (HTTP push)
```

### Grafana Starter Dashboard Panels

1. **Trace Search** (Tempo datasource) — query by service name; shows recent traces
2. **smoke.counter total** (Prometheus datasource) — single-stat panel for the smoke counter
3. **Recent Logs** (Loki datasource) — last 100 lines from `{job="otel-app"}`

### Edge Cases and Failure Modes

- **Collector not ready when smoke test runs:** smoke test should retry for up to
  10s before failing; add a short `time.sleep` + loop or use OTEL SDK's built-in
  retry exporter config.
- **Tempo not yet indexing:** Tempo has a short ingestion delay; smoke test prints
  the trace ID so it can be pasted directly into Tempo's search if the panel doesn't
  show it immediately.
- **Port conflicts:** document default ports in README (`3000` Grafana, `4317` OTLP,
  `3200` Tempo, `9090` Prometheus, `3100` Loki); no port remapping in Compose for now.
- **Windows Docker volumes:** `grafana/provisioning` and config dirs use relative
  paths in Compose bind mounts — works on Docker Desktop for Windows.

### Deferred to Later Commits

- All pipeline services (gateway, transcription, diarization, indexing, storage)
- MCP server
- Claude Code skill
- `docker-compose.dev.yml` overlay
- `Makefile` / `justfile`

---

## Commit 2 — Pipeline Services

### Scope

Addresses all Story 2 acceptance criteria:
- Five FastAPI services: gateway, transcription, diarization, indexing, storage
- End-to-end distributed trace across all five via W3C TraceContext propagation
- Per-service span attributes and metrics as specified
- Structured JSON logs with `trace_id` embedded (enables Grafana log↔trace correlation)
- Simulated delays and error rates configurable via environment variables
- All services containerized and wired into `docker-compose.yml`
- Repo directory restructure: infra configs move to `infra/`, app stays at root

### Approach

Each service is a FastAPI app instrumented with two OTEL auto-instrumentation
libraries: `opentelemetry-instrumentation-fastapi` (creates a span per incoming
request, extracts incoming TraceContext) and `opentelemetry-instrumentation-httpx`
(injects TraceContext into outgoing HTTP calls). This means W3C trace propagation
is handled entirely by the instrumentation libraries — no manual header passing
in application code. The gateway calls each downstream service sequentially via
`httpx.AsyncClient`, producing a single trace with a child span per hop.

`otel_common` is updated to add structured JSON logging with trace_id/span_id
injected from the active span context. Every `logger.info(...)` call automatically
includes the current trace ID in the JSON body, enabling one-click log→trace
navigation in Grafana.

All services are built with the repo root as the Docker build context so the
shared `otel_common/` package can be copied in without duplication.

Infra configs (`otel-collector/`, `tempo/`, `prometheus/`, `loki/`, `grafana/`)
move to an `infra/` subdirectory to separate platform concerns from app concerns.
`docker-compose.yml` stays at the repo root and references `./infra/...` paths —
one compose file, no network split, no operational complexity. `scripts/` stays
at the root alongside the app code; the smoke test is an app-level concern (it
exercises the pipeline), not an infra concern.

### Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Trace propagation | OTEL auto-instrumentation (FastAPI + HTTPX) | Zero manual header code; teaches that instrumentation libraries do the heavy lifting |
| HTTP client | `httpx.AsyncClient` | Async-native, compatible with FastAPI; HTTPX instrumentation is first-class in OTEL Python |
| Pipeline sequencing | Sequential calls in gateway | Linear trace waterfall is easier to read in Tempo than parallel fan-out |
| Log format | Structured JSON with `trace_id` and `span_id` in body | Grafana derived fields regex can extract trace_id from log line for one-click correlation |
| Log correlation impl | `_TraceContextFilter` in `otel_common` + `StreamHandler` with JSON formatter | Keeps correlation logic in one place; adds stdout logging alongside OTLP (useful for `docker compose logs`) |
| Docker build context | Repo root for all services | Allows `COPY otel_common/` into each service image without duplication |
| Storage backend | In-memory `dict` in `storage-svc` | Simplest possible; resets on restart (fine for demo); no extra deps |
| Error simulation | `indexing-svc` only, via `SIM_ERROR_RATE` env var | Simulates LLM unreliability; shows error spans in Tempo |

### Service Layout

```
services/
  gateway/       main.py  requirements.txt  Dockerfile   port 8000
  transcription/ main.py  requirements.txt  Dockerfile   port 8001
  diarization/   main.py  requirements.txt  Dockerfile   port 8002
  indexing/      main.py  requirements.txt  Dockerfile   port 8003
  storage/       main.py  requirements.txt  Dockerfile   port 8004
```

### API Contracts

```
POST /jobs (gateway)
  body: { filename: str, duration_seconds: float }
  → calls transcription → diarization → indexing → storage
  response: { job_id: str, transcript_id: str, status: "complete" }

POST /transcribe (transcription)
  body: { filename: str, duration_seconds: float }
  response: { transcript_id: str, text: str, word_count: int }

POST /diarize (diarization)
  body: { transcript_id: str, text: str }
  response: { transcript_id: str, speakers: [{name, word_count}], segment_count: int }

POST /index (indexing)
  body: { transcript_id: str, text: str, speakers: list }
  response: { transcript_id: str, tags: [str], summary: str, model: str, tokens_used: int }

POST /transcripts (storage) — store
  body: { transcript_id, filename, text, speakers, tags, summary }
  response: { id: str, created_at: str }

GET /transcripts (storage) — list
  response: [{ id, filename, tags, created_at }]

GET /transcripts/{id} (storage) — retrieve
  response: full transcript object

GET /health (all services)
  response: { status: "ok", service: str }
```

### Distributed Trace Shape

A single `POST /jobs` produces one trace visible in Tempo:
```
[gateway]      POST /jobs                    ~1.5s total
  [gateway]    POST transcription:8001/...  ~0.4s  ← injected by HTTPX instrumentation
    [transcription] POST /transcribe        ~0.4s  ← extracted by FastAPI instrumentation
  [gateway]    POST diarization:8002/...    ~0.3s
    [diarization]   POST /diarize           ~0.3s
  [gateway]    POST indexing:8003/...       ~0.8s
    [indexing]      POST /index             ~0.8s
  [gateway]    POST storage:8004/...        ~0.1s
    [storage]       POST /transcripts       ~0.1s
```

### OTEL Instrumentation Per Service

| Service | Manual span attributes | Metrics |
|---|---|---|
| gateway | — | — |
| transcription | `transcript.word_count` (int) | histogram `transcription.duration_seconds` |
| diarization | `diarization.speaker_count` (int) | counter `diarization.segments_total` |
| indexing | `indexing.model` (str), `indexing.tokens_used` (int) | histogram `indexing.llm_tokens_used` |
| storage | — | counter `storage.transcripts_stored_total` |

Manual span attributes are set on the span created by FastAPI auto-instrumentation
via `trace.get_current_span().set_attribute(...)`. No manual `start_span` needed.

### File and Component Changes

| File | Change |
|---|---|
| `infra/` | New directory; `otel-collector/`, `tempo/`, `prometheus/`, `loki/`, `grafana/` move here |
| `docker-compose.yml` | Update all infra volume bind-mount paths from `./X` to `./infra/X`; add five app services |
| `otel_common/__init__.py` | Add `_TraceContextFilter` and JSON `StreamHandler`; update `_setup_logs` |
| `services/gateway/main.py` | FastAPI app; orchestrates pipeline via `httpx.AsyncClient` |
| `services/transcription/main.py` | Simulates ASR; sets `transcript.word_count`; records duration histogram |
| `services/diarization/main.py` | Simulates speaker attribution; sets `diarization.speaker_count`; increments segments counter |
| `services/indexing/main.py` | Simulates LLM call with configurable error rate; sets `indexing.model`; records token histogram |
| `services/storage/main.py` | In-memory transcript store; increments stored counter; exposes list + get endpoints |
| `services/*/requirements.txt` | `fastapi`, `uvicorn[standard]`, `httpx`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx` + SDK deps |
| `services/*/Dockerfile` | `FROM python:3.12-slim`; build context = repo root; `COPY otel_common/` + service files |
| `docker-compose.yml` | Add gateway, transcription, diarization, indexing, storage services with healthchecks and env vars |
| `grafana/provisioning/datasources/datasources.yaml` | Update Loki derived field regex to match `"trace_id":"([a-f0-9]+)"` in JSON log body |

### Environment Variables

| Variable | Default | Services |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | all |
| `SIM_DELAY_MIN` | `0.1` | transcription, diarization, indexing, storage |
| `SIM_DELAY_MAX` | `0.8` | transcription, diarization, indexing |
| `SIM_ERROR_RATE` | `0.0` | indexing only |
| `TRANSCRIPTION_URL` | `http://transcription:8001` | gateway |
| `DIARIZATION_URL` | `http://diarization:8002` | gateway |
| `INDEXING_URL` | `http://indexing:8003` | gateway |
| `STORAGE_URL` | `http://storage:8004` | gateway |

### Edge Cases and Failure Modes

- **Indexing error simulation:** when `random() < SIM_ERROR_RATE`, `indexing-svc`
  raises HTTP 503; gateway propagates the error; the span is recorded with
  `status=ERROR` — visible as a red span in Tempo. Good teaching moment.
- **Service startup ordering:** gateway `depends_on` all downstream services with
  `service_healthy`; downstream services `depends_on` `otel-collector`.
- **Cold-start latency:** first request after `docker compose up` may be slow as
  gRPC channels initialize; subsequent requests are fast.
- **In-memory storage reset:** `storage-svc` data is lost on container restart;
  documented in README; the seed script (Story 4) addresses this for demos.

### Deferred to Later Commits

- MCP server (Story 3)
- Claude Code skill and `docker-compose.dev.yml` (Story 4)
- `Makefile` / `justfile` (Story 4)
- Seed script (Story 4)
- Seed script
