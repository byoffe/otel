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
