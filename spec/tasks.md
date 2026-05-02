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
