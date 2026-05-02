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
- Seed script
