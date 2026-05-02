# Requirements: OTEL Conference Transcript Pipeline

## Problem

OpenTelemetry is the standard for observability in modern distributed systems, but
it's invisible until you have something to watch. MCP (Model Context Protocol) is
the emerging standard for AI tool integration, but it's abstract until you can talk
to a real system through it. This project makes both concrete by building a realistic
(simulated) ML pipeline in a familiar domain — conference audio processing — and
instrumenting every layer of it.

The cost of not doing this: these concepts stay theoretical. A working system you
built yourself is worth ten blog posts.

## Vision

A simulated conference transcript processing pipeline, implemented as a set of Python
microservices, fully instrumented with OpenTelemetry. When a client submits an "audio
file" (a stub), the request fans out through transcription, speaker diarization, LLM
indexing, and storage — each service adding OTEL spans, metrics, and log records.
Every hop is visible in Grafana: traces in Tempo, metrics in Prometheus, logs in Loki.

An MCP server wraps the storage service so that an AI agent (Claude) can interrogate
transcripts conversationally. A Claude Code skill documents the interaction model so
the CLI is self-describing.

The project is a learning artifact: every OTEL concept (span, trace context propagation,
metrics instruments, structured logs) appears in the code at least once, with enough
scaffolding that someone coming to observability fresh can see exactly where each signal
enters the code and where it surfaces in the UI.

## Goals

1. A local observability stack (OTEL Collector + Tempo + Prometheus + Loki + Grafana)
   runs via a single `docker compose up`.
2. Grafana comes up with all three datasources pre-wired and a starter dashboard.
3. A Python project scaffold with `venv` + `pip`, `ruff` for lint/format, and
   `pyright` for type checking.
4. GitHub Actions CI runs lint, format check, and type check on every push and PR.
5. A minimal smoke-test script emits one trace, one metric counter, and one structured
   log record through the OTEL SDK, and all three appear in Grafana.
6. A `gateway-svc` (FastAPI) accepts a simulated audio submission and orchestrates
   the pipeline, propagating trace context downstream.
7. A `transcription-svc` (FastAPI) simulates ASR with a configurable delay and emits
   a span with token-count and duration attributes.
8. A `diarization-svc` (FastAPI) simulates speaker attribution with a delay and emits
   per-speaker segment metrics.
9. An `indexing-svc` (FastAPI) simulates an LLM call (configurable latency, error rate)
   and emits a histogram of "LLM token cost".
10. A `storage-svc` (FastAPI) persists transcripts in-memory (SQLite optional) and
    serves a REST retrieval API; emits storage operation metrics.
11. Trace context is propagated across all service hops via W3C TraceContext headers —
    a single submitted job produces one end-to-end trace visible in Tempo.
12. An MCP server (FastMCP) wraps the `storage-svc` API, exposing tools for listing,
    retrieving, and searching transcripts. Claude can be connected to it via MCP config.
13. A Claude Code skill (`/transcripts`) describes the interaction model: how to submit
    a job, query results, and interpret the traces.
14. A `docker-compose.dev.yml` overlay mounts service source trees for live reload
    during development.
15. All services and the MCP server are containerized; `docker compose up` starts
    the full system.
16. A seed script populates `storage-svc` with realistic fake transcripts so the MCP
    demo works immediately without running the pipeline.

## Acceptance Criteria

### Story 1 — Observability Infrastructure + Project Scaffold

- [ ] Running `docker compose up` starts OTEL Collector, Tempo, Prometheus, Loki, and
  Grafana with no manual configuration.
- [ ] Grafana is reachable at `http://localhost:3000` and has Tempo, Prometheus, and
  Loki datasources provisioned automatically (no manual setup).
- [ ] A starter Grafana dashboard is provisioned showing: a trace search panel (Tempo),
  a metric panel (Prometheus), and a log panel (Loki).
- [ ] The Python project root has `pyproject.toml` with `ruff` and `pyright` as dev
  dependencies; a `requirements-dev.txt` is generated from it for CI convenience.
- [ ] `ruff check .` and `ruff format --check .` pass on the initial scaffold with
  zero violations.
- [ ] `pyright` passes on the initial scaffold.
- [ ] GitHub Actions workflow runs on push and PR to `main`; job fails if lint, format,
  or type checks fail.
- [ ] Given the stack is running, when `python scripts/smoke_test.py` is run, then a
  trace appears in Tempo's search UI within 10 seconds.
- [ ] Given the stack is running, when `python scripts/smoke_test.py` is run, then a
  metric named `otel.smoke.counter` appears in Prometheus/Grafana within 30 seconds.
- [ ] Given the stack is running, when `python scripts/smoke_test.py` is run, then a
  structured log line appears in Loki's Explore UI within 30 seconds.
- [ ] `README.md` documents: prerequisites (Docker, Python + venv), how to start the
  stack, how to run the smoke test, and where to find each signal in Grafana.

### Story 2 — Pipeline Services (gateway → transcription → diarization → indexing → storage)

- [ ] Each service starts as a FastAPI app with health check at `GET /health`.
- [ ] Given all services are running, when a `POST /jobs` is submitted to gateway-svc
  with a fake audio filename, then an end-to-end trace spanning all five services
  appears in Tempo.
- [ ] Each service-to-service call propagates W3C TraceContext headers so all spans
  share one trace ID.
- [ ] `transcription-svc` emits a span attribute `transcript.word_count` and a
  histogram metric `transcription.duration_seconds`.
- [ ] `diarization-svc` emits a span attribute `diarization.speaker_count` and a
  counter metric `diarization.segments_total`.
- [ ] `indexing-svc` emits a span attribute `indexing.model` and a histogram metric
  `indexing.llm_tokens_used`.
- [ ] `storage-svc` emits a counter metric `storage.transcripts_stored_total`.
- [ ] Each service logs at least one structured log record per request (with trace_id
  and span_id in the log body so Grafana can correlate logs↔traces).
- [ ] Simulated delays and error rates are configurable via environment variables.
- [ ] All services and their dependencies are declared in `docker-compose.yml`.

### Story 3 — MCP Server + Claude Integration

- [ ] A FastMCP server exposes tools: `list_transcripts`, `get_transcript`,
  `search_transcripts` (keyword search over tags and speaker names).
- [ ] The MCP server is runnable directly (`python -m mcp_server`) or as a container.
- [ ] Claude can be connected to the MCP server by adding it to `.claude/mcp.json`.
- [ ] Given the MCP server is running and connected, when asked "what transcripts are
  available?", Claude returns a list drawn from `storage-svc`.
- [ ] Given a transcript ID, Claude can retrieve and summarize a full transcript via
  the MCP tool.
- [ ] The MCP server emits OTEL spans for each tool invocation so AI-driven queries
  appear in the same Tempo trace view as pipeline runs.
- [ ] A seed script (`scripts/seed.py`) populates `storage-svc` with at least 5 fake
  transcripts so the MCP demo works without running the pipeline.

### Story 4 — Claude Code Skill + Developer Experience

- [ ] A `/transcripts` Claude Code skill documents: how to submit a job (`curl`
  examples), how to query via MCP, and how to navigate traces in Grafana.
- [ ] The skill includes a quick-reference table: signal type → where to find it in
  Grafana → what it means.
- [ ] `docker-compose.dev.yml` overlay mounts all service source trees and enables
  uvicorn `--reload` so code changes apply without rebuilding.
- [ ] A `Makefile` (or `justfile`) provides: `make up`, `make dev`, `make smoke`,
  `make seed`, `make logs`.

## Out of Scope

- Real audio processing (whisper, pyannote, actual LLMs) — all pipeline logic is
  simulated stubs with configurable delays.
- A web frontend — the CLI (curl + Claude via MCP) is the interface.
- Authentication or multi-tenancy on any service.
- Production deployment, Kubernetes, or cloud infra.
- Persistent storage beyond in-memory or SQLite (no Postgres, no S3).
- OTEL sampling configuration (always-on sampling is fine for a demo).
- OpenTelemetry metrics exemplars (nice to have, out of scope for now).
