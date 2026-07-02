<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# MAS Lab — Docker

Run the lab UI, controller API, benchmarks, and agent runtime **without** a local
Python/uv install. Use Docker for day-to-day use; use `uv run` / `task install`
when you are developing the framework itself.

## Quick start

```bash
cd docker
cp .env.example .env          # set OPENAI_API_KEY
docker compose up --build
```

- **UI:** http://localhost:8080
- **API:** http://localhost:8090 (`/api/health`, `/api/registry`, …)

## Volume mounts

Two host folders are mounted into every backend/cli container:

| Container path | Env var (host path) | Purpose |
|----------------|---------------------|---------|
| `/workspace` | `MAS_WORKSPACE_MOUNT` (default: `..`) | `labs/`, `infra/`, project `.env` (optional `config.yaml`) |
| `/data` | `MAS_DATA_MOUNT` (default: `./data`) | Trace cache, benchmark outputs, run artifacts |

Example `.env` for a custom project:

```bash
MAS_WORKSPACE_MOUNT=/home/you/my-mas-project
MAS_DATA_MOUNT=/home/you/mas-lab-data
OPENAI_API_KEY=sk-...
```

`docker/data/` is created automatically as the default data directory (gitignored
contents; only `.gitkeep` is tracked).

### Workspace config priority

Inside the container, `MAS_WORKSPACE_ROOT=/workspace` is set. The runtime loads
`config.yaml` from the mounted workspace when present; otherwise the
entrypoint falls back to the baked copy from
[`examples/sample-workspace/config.yaml`](../examples/sample-workspace/config.yaml)
at `/opt/mas-lab/config.yaml`. Project config wins over `$XDG_CONFIG_HOME/mas/config.yaml` fallback.

To also use a host user config, bind-mount the XDG config tree:

```yaml
# compose override
services:
  backend:
    volumes:
      - ${XDG_CONFIG_HOME:-~/.config}/mas:/root/.config/mas
```

## Environment variables

| Variable | Default (container) | Purpose |
|----------|---------------------|---------|
| `OPENAI_API_KEY` | — | LLM API key in `docker/.env` (canonical; shell exports are ignored) |
| `MAS_WORKSPACE_ROOT` | `/workspace` | Directory for `config.yaml` discovery |
| `MAS_DATA_ROOT` | `/data` | Root for lab data |
| `MAS_TRACE_CACHE` | `/data/trace-cache` | Benchmark trace cache |
| `MAS_LABS_ROOT` | `/data/labs` | Experiment outputs under labs hierarchy |
| `MAS_RUNS_ROOT` | `/data/runs` | Agent session folders |
| `MAS_CONTROLLER_PORT` | `8090` | Controller HTTP port |
| `VITE_API_BASE_URL` | `http://localhost:8090` | API URL injected into the UI (browser-side) |

Secrets belong in `docker/.env` (gitignored). Shell `export OPENAI_API_KEY=…` is
**not** passed into containers — this avoids stale keys from another terminal or
project. After editing `docker/.env`, run `task restart`. Never commit API keys.

For one-off overrides (CI): `docker compose --env-file /path/to/secrets.env up`.

## Run modes

The backend image installs all CLIs (`mas-lab`, `mas-runtime`, `mas-ctl`).

### Controller + UI (default)

```bash
docker compose up --build
```

### One-off CLI commands

Use `docker compose run` with the `tools` profile (or `run backend` with an
explicit command — both share the same image and mounts):

```bash
# Benchmark
docker compose run --rm cli mas-lab config
docker compose run --rm cli mas-lab benchmark run \
  labs/design-space.lab/experiments/react-vs-cot.yaml --progress

# Single agent
docker compose run --rm cli mas-runtime run-agent \
  trash/agents/simple_qa_agent.yaml -q "Hello"

# MAS orchestration
docker compose run --rm cli mas-ctl run-mas path/to/mas.yaml -q "Hello"
```

Equivalent without the `cli` service:

```bash
docker compose run --rm backend mas-lab config
```

### Configure from inside Docker

1. Copy [`examples/sample-workspace/config.yaml`](../examples/sample-workspace/config.yaml)
   to your project root, or edit an existing copy under `MAS_WORKSPACE_MOUNT`.
2. Put secrets in `docker/.env` or `/workspace/.env`.
3. Restart: `task restart` from the repo root (rebuild + recreate both services).

Check effective paths:

```bash
docker compose run --rm cli mas-lab config
```

## Development with live code mounts

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

`compose.dev.yaml` bind-mounts Python package sources into `/opt/mas-lab` so code
edits apply without rebuilding. Workspace and data mounts are unchanged.

## Layout

```
docker/
  compose.yaml          # UI + controller stack
  compose.dev.yaml      # optional live source mounts
  .env.example
  data/                 # default MAS_DATA_MOUNT target
  backend/
    Dockerfile
    entrypoint.sh
  ui/
    Dockerfile
    nginx.conf
    entrypoint-ui.sh
```

## Build only (images are not published to a registry)

Images must be built locally from this repository:

```bash
cd docker
cp .env.example .env
docker compose build
```

Clean rebuild (remove existing local tags first):

```bash
# from repo root:
task docker-rebuild
```

Or manually:

```bash
cd docker
docker compose down --rmi local
docker rmi mas-lab-backend:local mas-lab-ui:local 2>/dev/null || true
docker compose build --no-cache
```
