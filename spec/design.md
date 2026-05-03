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
- Seed script (Story 3)

---

## Commit 3 — Pipeline Analyst MCP + Grafana MCP Integration

### Scope

Replaces the original storage-wrapping MCP design with an observability-first approach:

- **Custom `pipeline-analyst` MCP** (FastMCP, Python): 4 tools that query the
  Tempo HTTP API directly, enabling Claude to find slow jobs, diagnose bottlenecks,
  and surface errors using real trace data
- **`grafana/mcp-grafana`** (official Grafana-maintained server): wired into
  `.claude/mcp.json` so Claude can query dashboards, Prometheus metrics, and Loki
  logs through the same Grafana instance — no custom code
- **`scripts/seed.py`**: posts 5 diverse demo transcripts to `storage-svc` so the
  stack has realistic data to analyze immediately

Together these create a full diagnostic loop:
1. `/meeting` generates a conversation → pipeline runs → spans appear in Tempo
2. Claude queries `pipeline-analyst` tools: "which jobs were slow? what's the bottleneck?"
3. Claude queries `grafana` tools: "show me the error rate metric" or "find logs for trace X"

### Approach

#### pipeline-analyst MCP

Four tools backed directly by Tempo's HTTP API (port 3200). Each tool wraps its
logic in a `tracer.start_as_current_span(...)` block — the resulting spans are
exported to the OTEL Collector alongside pipeline traces, so Claude's diagnostic
queries appear in Tempo as their own root traces.

The Tempo TraceQL search API accepts queries like
`{rootName="POST /jobs" && duration > 2000ms}` and returns trace summaries with
`traceID`, `durationMs`, and `rootServiceName`. The trace-detail API
(`GET /api/traces/{id}`) returns full span trees as OTLP protobuf JSON.

For the `get_trace_breakdown` tool, spans are filtered to `SPAN_KIND_SERVER` only
(the actual request handler per service, not gateway's outgoing CLIENT spans).
This gives a clean per-service wall-clock time that Claude can reason about:
*"indexing-svc took 1.2s, everything else was under 500ms."*

Transport: stdio by default (Claude Code spawns `python -m mcp_server`). Docker
Compose adds it as an SSE service on port 8005 for use in longer-running sessions.
`__main__.py` calls `force_flush()` on exit to ensure spans reach Tempo even in
the short-lived stdio process.

#### grafana/mcp-grafana

The Grafana-maintained MCP server (image: `ghcr.io/grafana/mcp-grafana`) wraps
Grafana's HTTP API. Configured via environment variables
(`GRAFANA_URL`, `GRAFANA_USERNAME`, `GRAFANA_PASSWORD`). In `.claude/mcp.json`
it runs as a stdio subprocess via `docker run --rm -i`, which pulls the image on
first use and requires no separate service.

An optional Docker Compose profile (`mcp-grafana`) is provided for persistent SSE
sessions; Claude Code can switch between stdio docker run and the SSE URL.

### Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| MCP target | Tempo (traces) not storage-svc (data) | Traces are the core observability artifact; wrapping storage-svc would duplicate the `/meeting search` skill |
| Tool granularity | 4 focused tools vs. one generic query | Named tools (`find_slow_jobs`, `get_trace_breakdown`) let Claude answer diagnostic questions without writing TraceQL |
| Span filter in breakdown | `SPAN_KIND_SERVER` only | Eliminates gateway's outgoing CLIENT spans from per-service timing; gives clean wall-clock per service |
| Gateway overhead | `total - sum(downstream)` | Surfaces routing/serialization cost without parsing every span |
| Grafana MCP transport | stdio via `docker run` in mcp.json | No extra port; image pulled on demand; works even if the compose stack isn't running |
| Compose grafana-mcp | Optional profile | Users who want persistent SSE can enable it without breaking the default stack |
| OTEL context | New root span per tool call | MCP invocations carry no upstream context; each diagnostic query is its own trace root |
| Seed data | 5 diverse transcripts with realistic tags | Demonstrates search and filtering across varied topics without running the full pipeline |

### Tool Contracts

```
list_recent_jobs(limit=20) → list[dict]
  Searches Tempo for recent POST /jobs traces.
  Returns: [{trace_id, duration_ms, started_at, root_service}]
  Span: mcp.tool="list_recent_jobs", mcp.result_count=N

get_trace_breakdown(trace_id) → dict
  Fetches full trace from Tempo; extracts SERVER span per service.
  Returns: {trace_id, total_ms, services: {svc: dur_ms, gateway-overhead-ms: N}}
  Span: mcp.tool="get_trace_breakdown", mcp.trace_id=...

find_slow_jobs(threshold_ms=3000) → list[dict]
  TraceQL: {rootName="POST /jobs" && duration > Nms}
  Returns: [{trace_id, duration_ms}]
  Span: mcp.tool="find_slow_jobs", mcp.threshold_ms=N, mcp.result_count=N

find_error_jobs() → list[dict]
  TraceQL: {rootName="POST /jobs" && status=error}
  Returns: [{trace_id, duration_ms}]
  Span: mcp.tool="find_error_jobs", mcp.result_count=N
```

### MCP Configuration (`.claude/mcp.json`)

```json
{
  "mcpServers": {
    "pipeline-analyst": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "env": {
        "TEMPO_URL": "http://localhost:3200",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"
      }
    },
    "grafana": {
      "command": "docker",
      "args": ["run", "--rm", "-i",
        "-e", "GRAFANA_URL=http://host.docker.internal:3000",
        "-e", "GRAFANA_USERNAME=admin",
        "-e", "GRAFANA_PASSWORD=admin",
        "ghcr.io/grafana/mcp-grafana:latest"
      ]
    }
  }
}
```

### Distributed Trace Shapes

```
[mcp-server]  mcp.list_recent_jobs      ~40ms
  [mcp-server]  GET tempo:3200/api/search   (httpx, auto-instrumented)

[mcp-server]  mcp.get_trace_breakdown   ~30ms
  [mcp-server]  GET tempo:3200/api/traces/{id}

[mcp-server]  mcp.find_slow_jobs        ~40ms
  [mcp-server]  GET tempo:3200/api/search   (TraceQL with duration filter)
```

Each tool call is a new root trace, visible in Tempo alongside pipeline traces.

### File and Component Changes

| File | Change |
|---|---|
| `mcp_server/__init__.py` | FastMCP app; `init_otel("mcp-server")`; 4 tools; Tempo HTTP client |
| `mcp_server/__main__.py` | Entry point; reads `MCP_TRANSPORT`; `force_flush()` on exit |
| `mcp_server/requirements.txt` | `fastmcp`, `httpx`, OTEL SDK + OTLP exporter |
| `mcp_server/Dockerfile` | Same pattern as services; `CMD ["python", "-m", "mcp_server"]` |
| `scripts/seed.py` | Posts 5 diverse transcripts directly to `storage-svc /transcripts` |
| `.claude/mcp.json` | `pipeline-analyst` (stdio) + `grafana` (docker run stdio) |
| `docker-compose.yml` | Add `pipeline-analyst` service (SSE, port 8005); add `mcp-grafana` service under `mcp-grafana` profile |
| `pyproject.toml` | Add `fastmcp` and `httpx` to dev deps so `python -m mcp_server` works from venv |

### Edge Cases and Failure Modes

- **Tempo not running:** `httpx.ConnectError` propagates as a FastMCP tool error; Claude sees the message and can suggest `docker compose up tempo`.
- **No traces in Tempo:** `list_recent_jobs` returns `[]`; Claude should suggest running `/meeting topic=...` to generate some.
- **Short-lived stdio process (spans not flushed):** `__main__.py` calls `TracerProvider.force_flush()` in a `finally` block; spans reliably reach Tempo.
- **mcp-grafana image pull on first use:** `docker run` fetches `ghcr.io/grafana/mcp-grafana:latest` on first invocation; subsequent calls use the local cache.
- **`host.docker.internal` on Linux:** Not automatically resolved on Linux Docker. The `.claude/mcp.json` comment notes to substitute the host's LAN IP if needed.

### Deferred to Later Commits

- Claude Code skill `/transcripts` (Story 4)
- `docker-compose.dev.yml` live-reload overlay (Story 4)
- `Makefile` / `justfile` (Story 4)

---

## Commit 2.5 — Baked-Content Pipeline + `/meeting` Skill

### Scope

- Fix three post-Commit-2 bugs discovered during live testing
- Suppress health check spans to keep Grafana dashboard clean
- Add an optional baked-content path through the full pipeline so a Claude skill
  can inject pre-written conversations without breaking the distributed trace
- Add `.claude/skills/meeting/` Claude Code skill: generate a spoken conversation
  on any topic and POST it through the pipeline; search stored transcripts

### Approach

#### Bug fixes

Three bugs surfaced when running the Commit 2 stack on a clean machine:

1. **`wget` not in `python:3.12-slim`** — all five service healthchecks used
   `wget` which is absent from the slim image. Fixed by replacing each healthcheck
   `test` with `python -c "import urllib.request; urllib.request.urlopen(...)"`.

2. **`httpx 1.0.dev3` breaking change** — pip's `--pre` flag (present in some
   Dockerfiles) caused the pre-release `httpx 1.0.dev3` to be installed, which
   removed `httpx.BaseTransport`. Fixed by pinning `httpx>=0.27.0,<1.0` in
   `services/gateway/requirements.txt`.

3. **`filename` is a reserved `LogRecord` attribute** — `logger.info(...,
   extra={"filename": body.filename})` raised `KeyError` at runtime because
   Python's `LogRecord` already has a `filename` field. Fixed by renaming the
   extra field to `audio_file` in gateway.

#### Health check span suppression

With the pipeline running, the Grafana "Recent Pipeline Traces" panel was filled
with `GET /health` traces from Docker's healthcheck probes. Two changes fix this:

- Add `OTEL_PYTHON_EXCLUDED_URLS=health` environment variable to all five app
  services in `docker-compose.yml`. The OTEL Python SDK reads this at startup and
  skips span creation for any URL matching the pattern.
- Update the Grafana dashboard Tempo query from `{}` to `{name !~ ".*health.*"}`
  and the Loki log panel selector from `{job="otel-smoke"}` to `{job=~".+-svc"}`.

The `excluded_urls` parameter on `FastAPIInstrumentor.instrument_app()` was also
tried but proved unreliable in the installed SDK version; the env var is the
authoritative fix.

#### Baked-content pipeline path

The five services simulate their work (random delays, fake text, random speakers,
random tags). To let a Claude skill inject real conversations while still running
the full pipeline and emitting OTEL spans, an optional `content` field is added
to `POST /jobs`. When present, each service uses the pre-baked values instead of
simulating:

- **gateway**: adds `ConversationContent` model; passes `baked_text`,
  `baked_speakers`, `baked_tags`, `baked_summary` to each downstream call
- **transcription**: if `baked_text` present, uses it verbatim; skips fake generation
- **diarization**: if `baked_speakers` present, creates real `Speaker` objects and
  counts actual dialogue turns instead of randomizing
- **indexing**: if both `baked_tags` and `baked_summary` present, uses them;
  sets `tokens_used = len(text.split()) * 2`
- **storage**: adds `summary` field to `TranscriptSummary` so the `/meeting search`
  mode can filter on it

All services still execute, sleep, and emit spans — the distributed trace is
unchanged. Only the content is pre-baked.

#### `/meeting` Claude Code skill

A directory-per-skill layout under `.claude/skills/meeting/` following the
Anthropic skill spec:

- `SKILL.md`: frontmatter with `name`, `description`, `when_to_use`,
  `argument-hint`, `arguments` (topic, participants, search), `user-invocable: true`,
  `allowed-tools: "Write Bash(python *)"`. Two modes documented: Generate and Search.
- `scripts/post_meeting.py`: template script with a placeholder `PAYLOAD` dict.
  Claude fills it in and writes the result to `/tmp/meeting_post.py`, then runs it.
- `scripts/search_transcripts.py`: fetches `GET /transcripts` from storage-svc and
  filters by query against tags, filename, and summary.

The `Write` tool is retained in `allowed-tools` because Generate mode writes the
filled-in script to `/tmp/` before running it.

### Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Baked-content transport | Optional `content` field on `POST /jobs` | Single entry point; all services opt-in gracefully; no new endpoints or routes |
| Storage `summary` in list response | Add to `TranscriptSummary` model | Enables the `/meeting search` skill to filter on outcome text, not just tags |
| Skill script temp path | `/tmp/meeting_post.py` | Avoids mutating the committed template; clean slate each invocation |
| Health span suppression | Env var `OTEL_PYTHON_EXCLUDED_URLS` | More reliable than the `excluded_urls` kwarg in the installed SDK version |
| Skill script separator char | ASCII `--` instead of `──` | Windows cp1252 codec cannot encode box-drawing characters; plain ASCII is safe |

### File and Component Changes

| File | Change |
|---|---|
| `docker-compose.yml` | All 5 app services: healthcheck `wget` → `python urllib`; add `OTEL_PYTHON_EXCLUDED_URLS=health` |
| `services/gateway/requirements.txt` | Pin `httpx>=0.27.0,<1.0` |
| `services/gateway/main.py` | `filename` log field → `audio_file`; add `ConversationContent` model; pass baked fields downstream |
| `services/transcription/main.py` | Accept `baked_text`; use verbatim when present |
| `services/diarization/main.py` | Accept `baked_speakers`; build real `Speaker` objects and count dialogue turns |
| `services/indexing/main.py` | Accept `baked_tags`, `baked_summary`; use when both present |
| `services/storage/main.py` | Add `summary` to `TranscriptSummary` model and list endpoint |
| `infra/grafana/dashboards/otel-overview.json` | Trace query `{name !~ ".*health.*"}`; log selector `{job=~".+-svc"}`; version bump |
| `.claude/skills/meeting/SKILL.md` | Skill entrypoint: frontmatter + Generate/Search mode instructions |
| `.claude/skills/meeting/scripts/post_meeting.py` | Template POST script |
| `.claude/skills/meeting/scripts/search_transcripts.py` | Transcript search script (ASCII separator for Windows compat) |

---

## Commit 4 — Richer Metrics, Collector-Derived Signals, and Production Dashboards

### Scope

- All four OTEL metric instrument types present in production code
- Collector-side `spanmetrics` connector deriving RED metrics from traces
- Prometheus exemplar storage enabled so metric data points link back to traces
- Three new Grafana dashboards replacing the starter panel with production-quality views

### New Metric Instruments

Every service gets at least one new instrument. The goal is a representative example
of every SDK type, not metric maximalism.

| Service | Instrument | Name | Type | Notes |
|---|---|---|---|---|
| gateway | UpDownCounter | `pipeline.jobs_in_flight` | UpDownCounter | +1 on request enter, -1 on exit (success or error) |
| gateway | Counter | `gateway.jobs_total` | Counter | Attributes: `status=success\|error` |
| transcription | Histogram | `transcription.word_count` | Histogram | Distribution of transcript lengths; teaches multiple histograms per service |
| diarization | Histogram | `diarization.processing_duration_seconds` | Histogram | Wall-clock time for diarization step; complements the existing counter |
| indexing | Counter | `indexing.errors_total` | Counter | Incremented on simulated failure; explicit error signal beyond span status |
| storage | ObservableGauge | `storage.transcripts_active` | ObservableGauge | Reports `len(_store)` via callback; teaches pull-style (observable) instruments |

`ObservableGauge` is the only pull-style instrument in the SDK — a callback is
registered once and the SDK calls it at each collection interval. Contrasted with
`Counter` and `Histogram` which are push-style (application calls `.add()` / `.record()`).
`UpDownCounter` completes the set: like Counter but can go negative (in-flight requests).

### Collector `spanmetrics` Connector

`spanmetrics` is a built-in OTEL Collector connector that reads the traces pipeline
and emits metrics. It requires zero application code changes — it derives metrics
from spans that already exist.

```
traces pipeline
  receivers: [otlp]
  exporters: [otlp/tempo, spanmetrics]   ← spanmetrics as trace consumer

metrics pipeline
  receivers: [otlp, spanmetrics]          ← spanmetrics as metric producer
  exporters: [prometheus]
```

What it emits (namespace `pipeline`):
- `pipeline_calls_total` — counter per span, labeled by `service_name`, `span_name`,
  `http_status_code`, `status_code` (OTEL status: OK / ERROR / UNSET)
- `pipeline_duration_bucket` — histogram of span durations, same labels

The gateway root span (`POST /jobs`, `service_name=gateway-svc`) has a duration equal
to the full end-to-end pipeline time. No new instrumentation required.

Configuration (in `infra/otel-collector/config.yaml`):
```yaml
connectors:
  spanmetrics:
    namespace: pipeline
    histogram:
      explicit:
        buckets: [0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    dimensions:
      - name: service.name
      - name: http.route
      - name: http.status_code
    metrics_flush_interval: 15s
```

### Exemplars

An exemplar is a specific trace ID attached to a histogram observation. When Grafana
renders a histogram panel with exemplars enabled, each data point shows a diamond
marker; clicking it opens the trace in Tempo. This creates a direct path from
"metric spike" → "offending trace".

Three components required:
1. **SDK**: `MeterProvider` configured with `AlwaysOnExemplarFilter` — the SDK then
   samples the current trace context and attaches it to histogram recordings.
2. **Prometheus**: `--enable-feature=exemplar-storage` flag in docker-compose command.
3. **Grafana panel**: `exemplarColor` set in panel definition.

`spanmetrics`-generated histograms carry exemplars automatically (they read span
context from the trace). Application histograms (`transcription.duration_seconds` etc.)
carry exemplars once the `AlwaysOnExemplarFilter` is set.

### Dashboard Design

Three dashboards replace the single `otel-overview.json` starter.

#### 1. Pipeline RED (`pipeline-red.json`)
Prometheus datasource. All queries from `spanmetrics` output — no application metrics.

| Panel | Type | Query |
|---|---|---|
| Request rate (req/s) | Time series | `rate(pipeline_calls_total{service_name=~".+"}[1m])` per service |
| Error rate (%) | Time series | `rate(pipeline_calls_total{status_code="STATUS_CODE_ERROR"}[1m]) / rate(pipeline_calls_total[1m])` |
| p50 / p95 / p99 latency | Time series | `histogram_quantile(0.95, rate(pipeline_duration_bucket[5m]))` |
| Requests today | Stat | `increase(pipeline_calls_total{http_route="/jobs"}[24h])` |
| Error count today | Stat | `increase(pipeline_calls_total{status_code="STATUS_CODE_ERROR"}[24h])` |

#### 2. Data Insights (`data-insights.json`)
Mix of Prometheus datasource (application metrics) and Loki (log counts).

| Panel | Type | Query |
|---|---|---|
| Word count distribution | Heatmap | `transcription_word_count_bucket` |
| Token usage over time | Time series | `rate(indexing_llm_tokens_used_sum[5m])` |
| Speaker count (bar) | Bar chart | `sum by (le) (indexing_llm_tokens_used_bucket)` |
| Transcripts stored | Gauge + trend | `storage_transcripts_active` (observable gauge, live) |
| Transcripts stored over time | Time series | `increase(storage_transcripts_stored_total[1h])` |
| Jobs in flight | Gauge | `pipeline_jobs_in_flight` |

#### 3. Pipeline Latency (`pipeline-latency.json`)
End-to-end and per-stage latency. SLO panel.

| Panel | Type | Query |
|---|---|---|
| End-to-end p50/p95/p99 | Time series | `histogram_quantile` on `pipeline_duration_bucket{service_name="gateway-svc"}` |
| Duration heatmap | Heatmap | `pipeline_duration_bucket{service_name="gateway-svc"}` |
| Per-stage median | Bar gauge | `histogram_quantile(0.5, ...)` per service |
| SLO: % under 5s | Stat | `(1 - rate(pipeline_duration_bucket{le="5"}[1h]) / rate(pipeline_duration_count[1h])) * 100` |
| Latency budget | Table | p50/p95/p99 per service side by side |

### Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Derived metrics source | `spanmetrics` connector | Zero application code change; teaches that the collector is a processing layer, not just a router |
| End-to-end duration signal | Gateway root span via `spanmetrics` | The gateway span already covers the full wall-clock time; no new "job timer" needed |
| Observable gauge in storage | `len(_store)` callback | Simplest meaningful gauge; contrasts pull-style with push-style instruments |
| Exemplar filter | `AlwaysOnExemplarFilter` | Always-on is correct for a demo; production would use `TraceBasedExemplarFilter` |
| Dashboard count | 3 focused dashboards | Each has one job (RED / data characteristics / latency); avoids "everything on one page" anti-pattern |
| Existing otel-overview.json | Retain with updates | Still useful as a "three signals" entry point; update to link to the new dashboards |

### File and Component Changes

| File | Change |
|---|---|
| `infra/otel-collector/config.yaml` | Add `spanmetrics` connector; wire into traces + metrics pipelines |
| `docker-compose.yml` | Add `--enable-feature=exemplar-storage` to Prometheus command |
| `otel_common/__init__.py` | Add `AlwaysOnExemplarFilter` to `MeterProvider` construction |
| `services/gateway/main.py` | Add `pipeline.jobs_in_flight` UpDownCounter; `gateway.jobs_total` Counter |
| `services/transcription/main.py` | Add `transcription.word_count` histogram |
| `services/diarization/main.py` | Add `diarization.processing_duration_seconds` histogram |
| `services/indexing/main.py` | Add `indexing.errors_total` Counter |
| `services/storage/main.py` | Add `storage.transcripts_active` ObservableGauge |
| `infra/grafana/dashboards/pipeline-red.json` | New: RED metrics dashboard |
| `infra/grafana/dashboards/data-insights.json` | New: data characteristics dashboard |
| `infra/grafana/dashboards/pipeline-latency.json` | New: latency + SLO dashboard |
| `infra/grafana/dashboards/otel-overview.json` | Update: add links to new dashboards |
| `tests/test_*.py` | Add tests for each new metric instrument |

### Edge Cases and Failure Modes

- **`spanmetrics` first-flush delay**: metrics don't appear in Prometheus until
  `metrics_flush_interval` (15s) after the first trace. Dashboard queries use
  `[5m]` rate windows; first result appears ~15–20s after first pipeline job.
- **No exemplars in OTEL SDK < 1.24**: `AlwaysOnExemplarFilter` was stabilised in
  1.24. `pyproject.toml` already pins `opentelemetry-sdk>=1.24` so this is safe.
- **Exemplar cardinality in Prometheus**: exemplars are stored per-bucket in TSDB
  with a fixed ring buffer (default 10 per series). For a demo, this is fine.
- **Grafana heatmap panel**: requires `format=heatmap` and bucket label matching;
  `spanmetrics` uses `le` labels compatible with Grafana's native histogram support.
