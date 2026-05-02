# Tasks: OTEL Conference Transcript Pipeline

## Commit 1 — Observability Infrastructure + Project Scaffold

### Python scaffold

- ✅ 1. Create `pyproject.toml` at repo root with `[tool.ruff]` (line-length=100,
         select=["E","F","I"]) and `[tool.pyright]` (pythonVersion="3.12", standard mode)
         sections; declare `ruff` and `pyright` as dev deps under
         `[project.optional-dependencies] dev`
- ✅ 2. Create `requirements-dev.txt` with `-e .[dev]` (installs project + all dev deps
         in one step via pyproject.toml)
- ✅ 3. Create `otel_common/__init__.py` with `init_otel(service_name: str) -> None`
         that configures `TracerProvider`, `MeterProvider`, and `LoggerProvider` all
         pointing at the OTLP gRPC endpoint from env var
         `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://localhost:4317`)
- ✅ 4. Create `.gitignore` covering: `.venv/`, `__pycache__/`, `*.pyc`, `.env`,
         `.DS_Store`, `*.egg-info/`

### Docker Compose observability stack

- ✅ 5. Create `otel-collector/config.yaml` defining:
         - receiver: `otlp` (grpc port 4317, http port 4318)
         - exporters: `otlp/tempo` (traces), `prometheus` scrape endpoint (metrics),
           `loki` (logs); `health_check` extension on port 13133
         - pipelines wiring receivers → exporters for traces, metrics, logs
- ✅ 6. Create `tempo/tempo.yaml` with local storage backend, OTLP receiver enabled
- ✅ 7. Create `prometheus/prometheus.yml` with scrape config targeting the OTEL
         Collector's metrics endpoint (`otel-collector:8889`)
- ✅ 8. Create `loki/loki-config.yaml` with filesystem storage and default retention
- ✅ 9. Create `grafana/provisioning/datasources/datasources.yaml` provisioning
         Tempo (port 3200), Prometheus (port 9090), and Loki (port 3100) as datasources
- ✅ 10. Create `grafana/provisioning/dashboards/dashboards.yaml` pointing at
          `/var/lib/grafana/dashboards`
- ✅ 11. Create `grafana/dashboards/otel-overview.json` with three panels:
          trace table (Tempo, `table` type — the `traces` panel type is unreliable in
          dashboards; use Explore → Tempo for interactive trace search), metric stat
          (Prometheus), recent logs (Loki)
- ✅ 12. Create `docker-compose.yml` with services: `otel-collector`, `tempo`,
          `prometheus`, `loki`, `grafana`; bind-mount all config files; define
          a shared `observability` network; healthchecks on all services

### Smoke test

- ✅ 13. Create `scripts/smoke_test.py` that:
          - calls `init_otel("otel-smoke")`
          - starts a span named `"smoke.operation"`, adds attribute
            `smoke.run = "true"`, ends it
          - increments a counter named `otel.smoke.counter`
          - emits one structured log record at INFO level with field
            `event = "smoke_test_complete"`
          - prints the trace ID so it can be pasted into Tempo search
          - flushes all providers before exit

### CI

- ✅ 14. Create `.github/workflows/ci.yml` with a single job `lint` that:
          - triggers on push and pull_request to `main`
          - checks out code, sets up Python 3.12, installs from `requirements-dev.txt`
          - runs `ruff check .`
          - runs `ruff format --check .`
          - runs `pyright`

### Docs

- ✅ 15. Create `README.md` covering: prerequisites (Docker Desktop, Python 3.12,
          `python -m venv .venv`), `docker compose up`, running the smoke test,
          a port reference table, and a "Where to find each signal in Grafana" section

## Notes

- Keep `otel_common/` free of FastAPI or service-specific imports — it will be
  copied into every service's Docker build context in Commit 2.
- The smoke test should tolerate the Collector not being available and print a
  clear error rather than hanging; OTEL SDK's default timeout is 10s per batch.
- Grafana admin credentials: `admin` / `admin` (document in README; fine for local dev).
- Tempo's default port for the UI/API is 3200; Grafana queries it there. The OTLP
  receiver inside Tempo also listens on 4317 but that port is owned by the Collector
  in this compose — Tempo gets traces forwarded from the Collector, not directly.

---

## Commit 2 — Pipeline Services

### Repo restructure

- ✅ 1. Create `infra/` directory and move `otel-collector/`, `tempo/`, `prometheus/`,
         `loki/`, and `grafana/` into it (git mv to preserve history)
- ✅ 2. Update all bind-mount paths in `docker-compose.yml` from `./X/` to `./infra/X/`
         for the five infra services; verify `docker compose config` shows no path errors

### otel_common update

- ✅ 3. Add `_TraceContextFilter` class to `otel_common/__init__.py`: a
         `logging.Filter` that reads the active span context and sets `trace_id`
         (32-char hex) and `span_id` (16-char hex) on every `LogRecord`
- ✅ 4. Add a JSON `StreamHandler` to `_setup_logs`: formats each log line as
         `{"service":"…","level":"…","msg":"…","trace_id":"…","span_id":"…"}`;
         attach the `_TraceContextFilter` to it; add to root logger alongside the
         existing `LoggingHandler` (OTLP path unchanged)
- ✅ 5. Update `grafana/provisioning/datasources/datasources.yaml` Loki derived
         field `matcherRegex` to `"trace_id":"([a-f0-9]+)"` to match the JSON log
         body format

### Service scaffolding (repeat pattern for all five services)

- ✅ 6. Create `services/gateway/requirements.txt`: `fastapi`, `uvicorn[standard]`,
         `httpx`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`,
         `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx`
- ✅ 7. Create `services/gateway/Dockerfile`: `FROM python:3.12-slim`, build context
         is repo root; `COPY otel_common/` then service files; `CMD uvicorn main:app`
- ✅ 8. Repeat tasks 6–7 for transcription, diarization, indexing, storage
         (identical requirements except port; indexing adds no extra deps)

### Service implementations

- ✅ 9. Create `services/storage/main.py`: FastAPI app with in-memory `dict` store;
         routes: `POST /transcripts`, `GET /transcripts`, `GET /transcripts/{id}`,
         `GET /health`; increments counter `storage.transcripts_stored_total` on store;
         calls `init_otel("storage-svc")` and `FastAPIInstrumentor.instrument_app(app)`
         at startup
- ✅ 10. Create `services/transcription/main.py`: `POST /transcribe` simulates ASR
          via `asyncio.sleep(uniform(SIM_DELAY_MIN, SIM_DELAY_MAX))`; generates fake
          text and word count; sets span attribute `transcript.word_count`; records
          histogram `transcription.duration_seconds`; logs one structured record
- ✅ 11. Create `services/diarization/main.py`: `POST /diarize` simulates speaker
          attribution; generates 2–4 fake speakers with segment counts; sets span
          attribute `diarization.speaker_count`; increments counter
          `diarization.segments_total` by segment count; logs one structured record
- ✅ 12. Create `services/indexing/main.py`: `POST /index` simulates LLM call;
          if `random() < SIM_ERROR_RATE` raises HTTP 503 (span status=ERROR);
          otherwise generates fake tags and summary; sets span attributes
          `indexing.model` and `indexing.tokens_used`; records histogram
          `indexing.llm_tokens_used`; logs one structured record
- ✅ 13. Create `services/gateway/main.py`: `POST /jobs` orchestrates the pipeline
          sequentially using `httpx.AsyncClient`; calls transcription → diarization
          → indexing → storage in order; propagates errors from downstream as HTTP
          502; logs one structured record per job with final transcript_id

### Docker Compose wiring

- ✅ 14. Add five app services to `docker-compose.yml` with:
          - `build: { context: ., dockerfile: services/<name>/Dockerfile }`
          - `OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317`
          - `SIM_DELAY_MIN`, `SIM_DELAY_MAX` env vars with defaults
          - `SIM_ERROR_RATE: 0.0` for indexing-svc
          - service URL env vars on gateway (TRANSCRIPTION_URL etc.)
          - healthcheck on `GET /health`
          - `depends_on: otel-collector: condition: service_healthy`
          - gateway additionally `depends_on` all four downstream services

### Verification

- ✅ 15. Run `docker compose up --build -d`, wait for all services healthy,
          then `curl -s -X POST http://localhost:8000/jobs \
          -H 'Content-Type: application/json' \
          -d '{"filename":"test.wav","duration_seconds":3600}' | python -m json.tool`
          — confirm a `transcript_id` is returned
- ✅ 16. In Grafana → Explore → Tempo, run TraceQL `{}` — confirm a trace with
          spans from all five services (`gateway-svc`, `transcription-svc`,
          `diarization-svc`, `indexing-svc`, `storage-svc`) appears
- ✅ 17. In Grafana → Explore → Loki, run `{job="gateway-svc"}` — confirm a log
          line with `trace_id` field appears; click "View Trace in Tempo" link

## Notes

- Storage runs on port 8004 with no persistent volume — data resets on restart.
- `FastAPIInstrumentor.instrument_app(app)` must be called AFTER `init_otel()` so
  the TracerProvider is already set when the instrumentation registers its middleware.
- `HTTPXClientInstrumentor().instrument()` is called once at module level in gateway;
  it patches all `httpx.AsyncClient` instances globally.
- The JSON `StreamHandler` added to `otel_common` writes to stdout — visible via
  `docker compose logs <service>` — and is separate from the OTLP log path to Loki.
  Both run in parallel; stdout is for developer convenience, OTLP is for Grafana.

---

---

## Commit 2.5 — Baked-Content Pipeline + `/meeting` Skill

### Bug fixes

- ✅ 1. Replace `wget` healthchecks with `python -c "import urllib.request; urllib.request.urlopen(...)"` in all five app services in `docker-compose.yml` (python:3.12-slim has no wget)
- ✅ 2. Pin `httpx>=0.27.0,<1.0` in `services/gateway/requirements.txt` to prevent pip from installing the breaking pre-release httpx 1.0.dev3
- ✅ 3. Rename `extra={"filename": ...}` → `extra={"audio_file": ...}` in `services/gateway/main.py` to avoid collision with the reserved `LogRecord.filename` attribute

### Health check span suppression

- ✅ 4. Add `OTEL_PYTHON_EXCLUDED_URLS=health` environment variable to all five app services in `docker-compose.yml`
- ✅ 5. Update `infra/grafana/dashboards/otel-overview.json`: trace panel query `{}` → `{name !~ ".*health.*"}`; log panel selector `{job="otel-smoke"}` → `{job=~".+-svc"}`; bump dashboard version

### Baked-content pipeline

- ✅ 6. Add `ConversationContent` Pydantic model and optional `content: ConversationContent | None` field to `JobRequest` in `services/gateway/main.py`; pass `baked_text`, `baked_speakers`, `baked_tags`, `baked_summary` in downstream service calls when present
- ✅ 7. Add `baked_text: str | None = None` to `TranscribeRequest` in `services/transcription/main.py`; use verbatim when present, skipping fake generation
- ✅ 8. Add `baked_speakers: list[dict[str, Any]] | None = None` to `DiarizeRequest` in `services/diarization/main.py`; build real `Speaker` objects and count actual dialogue turns when present
- ✅ 9. Add `baked_tags` and `baked_summary` fields to `IndexRequest` in `services/indexing/main.py`; use both when present; set `tokens_used = len(text.split()) * 2`
- ✅ 10. Add `summary: str` to `TranscriptSummary` model and `GET /transcripts` list response in `services/storage/main.py`

### `/meeting` Claude Code skill

- ✅ 11. Create `.claude/skills/meeting/SKILL.md` with full frontmatter (`name`, `description`, `when_to_use`, `argument-hint`, `arguments` block for topic/participants/search, `user-invocable: true`, `allowed-tools`) and two-mode (Generate / Search) instructions using `${CLAUDE_SKILL_DIR}/scripts/` paths
- ✅ 12. Create `.claude/skills/meeting/scripts/post_meeting.py`: placeholder `PAYLOAD` template that Claude fills in and POSTs to `http://localhost:8000/jobs`
- ✅ 13. Create `.claude/skills/meeting/scripts/search_transcripts.py`: fetches `GET /transcripts` and filters by query against tags, filename, and summary; uses ASCII `--` separator for Windows cp1252 compatibility

## Notes

- The baked-content path is fully opt-in: omitting `content` from `POST /jobs` leaves all five services in random-simulation mode. No existing behavior changes.
- Health span suppression confirmed working: same trace IDs in consecutive Tempo queries 15 s apart after adding `OTEL_PYTHON_EXCLUDED_URLS`.
- `search_transcripts.py` uses ASCII `--` (not `──`) because Python 3.14 on Windows defaults to cp1252, which cannot encode box-drawing characters.

---

## Commit 3 — Pipeline Analyst MCP + Grafana MCP Integration

### pipeline-analyst MCP server

- [ ] 1. Create `mcp_server/requirements.txt`: `fastmcp>=2.0`, `httpx>=0.27.0,<1.0`,
         `opentelemetry-sdk>=1.24.0`, `opentelemetry-exporter-otlp-proto-grpc>=1.24.0`
- [ ] 2. Create `mcp_server/Dockerfile`: `FROM python:3.12-slim`; build context = repo root;
         `COPY otel_common/ ./otel_common/`; install requirements; `COPY mcp_server/ ./mcp_server/`;
         `CMD ["python", "-m", "mcp_server"]`
- [ ] 3. Create `mcp_server/__init__.py`: FastMCP app `pipeline-analyst`; `init_otel("mcp-server")`;
         `TEMPO_URL` from env (default `http://localhost:3200`); 4 tools, each wrapped in
         `tracer.start_as_current_span(...)` with `mcp.tool` + result-count attributes:
         - `list_recent_jobs(limit=20)`: `GET /api/search?q={rootName="POST /jobs"}&limit=N`
         - `get_trace_breakdown(trace_id)`: `GET /api/traces/{id}`; filter `SPAN_KIND_SERVER`
           spans per service; return `{total_ms, services: {svc: dur_ms, gateway-overhead-ms: N}}`
         - `find_slow_jobs(threshold_ms=3000)`: TraceQL `{rootName="POST /jobs" && duration > Nms}`
         - `find_error_jobs()`: TraceQL `{rootName="POST /jobs" && status=error}`
- [ ] 4. Create `mcp_server/__main__.py`: read `MCP_TRANSPORT` (default `stdio`);
         call `mcp.run()` or `mcp.run(transport="sse", host="0.0.0.0", port=8005)`;
         `finally: force_flush()` on TracerProvider and MeterProvider

### Seed script

- [ ] 5. Create `scripts/seed.py`: define 5 diverse transcript dicts (different topics,
         tags, speakers); post each to `STORAGE_URL/transcripts` via `urllib.request`;
         print created IDs and filenames

### Docker Compose and MCP config

- [ ] 6. Add `pipeline-analyst` service to `docker-compose.yml`: build at repo root,
         `dockerfile: mcp_server/Dockerfile`; env `MCP_TRANSPORT=sse`, `MCP_PORT=8005`,
         `TEMPO_URL=http://tempo:3200`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`;
         port 8005; `depends_on: tempo: condition: service_healthy`
- [ ] 7. Add `mcp-grafana` service to `docker-compose.yml` under `profiles: [mcp-grafana]`:
         `image: ghcr.io/grafana/mcp-grafana:latest`; env `GRAFANA_URL=http://grafana:3000`,
         `GRAFANA_USERNAME=admin`, `GRAFANA_PASSWORD=admin`; port 3001;
         `depends_on: grafana`
- [ ] 8. Create `.claude/mcp.json`: register `pipeline-analyst` (stdio, `python -m mcp_server`,
         `TEMPO_URL=http://localhost:3200`); register `grafana` (stdio via
         `docker run --rm -i -e GRAFANA_URL=http://host.docker.internal:3000 ... ghcr.io/grafana/mcp-grafana:latest`)
- [ ] 9. Add `fastmcp>=2.0` and `httpx>=0.27.0,<1.0` to `[project.optional-dependencies] dev`
         in `pyproject.toml` so `python -m mcp_server` works from the dev venv

### Verification

- [ ] 10. `python scripts/seed.py` — confirm 5 IDs printed and
          `Invoke-RestMethod http://localhost:8004/transcripts` returns 5 records
- [ ] 11. `python -m mcp_server` (in a separate terminal) — confirm it starts without error
          and exits cleanly (stdio mode)
- [ ] 12. Ask Claude: "list recent pipeline jobs and tell me which was slowest" — confirm
          `list_recent_jobs` and `get_trace_breakdown` tools are invoked
- [ ] 13. Ask Claude: "find any jobs that took over 2 seconds" — confirm `find_slow_jobs`
          tool is invoked with `threshold_ms=2000`
- [ ] 14. In Tempo, confirm `pipeline-analyst` traces appear as separate root spans with
          `service.name="mcp-server"` alongside the pipeline `gateway-svc` traces
- [ ] 15. `docker compose up --build -d` — confirm `pipeline-analyst` container starts healthy

## Notes

- `python -m mcp_server` works from the repo root because `mcp_server/` is a package
  (has `__init__.py` + `__main__.py`). `TEMPO_URL` defaults to `http://localhost:3200`.
- `force_flush()` in `__main__.py` is critical for stdio mode: the process exits
  after each tool call and BatchSpanProcessor won't drain naturally.
- `get_trace_breakdown` filters to `SPAN_KIND_SERVER` spans to get clean per-service
  wall-clock times. The gateway has one SERVER span (the total) + CLIENT spans (outgoing
  calls); only the SERVER span is included, and gateway overhead is computed as
  `gateway_total - sum(downstream_server_spans)`.
- The `grafana` MCP entry uses `docker run --rm -i` (stdio), which pulls the image on
  first use. On Linux hosts, replace `host.docker.internal` with the host LAN IP.
