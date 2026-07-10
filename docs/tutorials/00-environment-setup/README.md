<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 0 — Environment Setup

> **Packages:** `mas-runtime`, `mas-ctl`, `mas-lab` (installed for you — Docker or `task install`)
> **Time:** ~10 min (Docker fast path) · ~20 min (developer path)
> **Goal:** Install MAS Lab, configure LLM access, and run your first
> `mas-ctl` commands before Tutorial 1.

---

## Choose your path

| Path | Best for | You need |
|------|----------|----------|
| **[Fast path — Docker only](#fast-path-docker-only)** | Users, demos, benchmarks | Docker, git, `OPENAI_API_KEY` for live LLM runs |
| **[Path A — Docker (full)](#path-a--docker-users)** | Same as fast path + CLI patterns, mounts, `task` helpers | Docker, optional [go-task](https://taskfile.dev/) |
| **[Path B — Developers](#path-b--developers-uv--task)** | Patching runtime, ctl, or lab | Python ≥ 3.11, `uv`, `task`, [direnv](https://direnv.net/) recommended |

Both paths use the **same manifests and tutorials**. Developers can still use Docker
for the UI (`task start`) while editing Python sources on the host.

**Infrastructure defaults** (`standard:openai`, `standard:ollama`, bundles, trace cache)
are documented in [§ Infrastructure](#infrastructure-llm-endpoints-and-data-paths) below —
not in the root README, because they only matter once you are setting up a run.

---

## Fast path — Docker only

No `uv`, no `task`, no direnv. You will configure LLM access, build the Docker
images, and run a few `mas-ctl` commands to confirm the install.

### 1 — Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine
- `git clone https://github.com/outshift-open/mas-lab.git && cd mas-lab`

### 2 — How LLM access works (read this first)

Three separate concerns — never mix secrets into YAML:

| Piece | What it is | Where it lives |
|-------|------------|----------------|
| **Infra manifest** | Non-secret endpoint config (API base URL, allowed models, `api_key_env` name) | `infra_refs` in `config.yaml` or `--infra-ref` on CLI |
| **Credential** | API key or token | `docker/.env` (Docker) or gitignored `.env` (developers) |
| **Flavour** | Runtime environment bundle (`local` = default in `library-standard`) | `mas_ctl.flavour` / `mas_lab.flavour` in workspace, or manifest |

**Copy-ready examples** (Tutorial 0 directory):

```bash
cp docs/tutorials/00-environment-setup/config.openai.example.yaml config.yaml
cp docs/tutorials/00-environment-setup/.env.example docker/.env   # Docker path
# Edit docker/.env — set OPENAI_API_KEY=sk-...
```

`config.openai.example.yaml` sets:

- `mas_ctl.flavour: local` and `mas_lab.flavour: local` (library-standard defaults)
- `infra_refs: [standard:openai]` — resolves to the bundled OpenAI `LLMProxy` manifest

**Bring your own infra manifest.** Drop a manifest in `~/.config/mas/infra/`
(e.g. `llm-proxy.yaml`) and reference it from `config.yaml`. Two keys work
together, and the difference trips people up:

- **`infra_refs`** — the list of manifests to *register* (make available). Each
  entry is a bundled ref (`standard:openai`, `standard:llm-proxy`) **or** a path
  to your own file (`~/.config/mas/infra/llm-proxy.yaml`). Override per-shell
  with `MAS_INFRA_REFS`; `--infra-ref` on the CLI still wins.
- **`default_infra`** — which registered manifest is *used by default* when a
  command doesn't name one. Set it to your manifest's path/ref so `mas-ctl chat`
  and `mas-lab benchmark` pick it up with no extra flag.

Keep secrets out of the file: a manifest can source both the endpoint and the
key from the environment — `api_base: env:LLM_PROXY_API_BASE|<fallback-url>` and
`api_key_env: OPENAI_API_KEY` (the key is read from that env var / `.env`, never
written in the manifest). See `~/.config/mas/infra/llm-proxy.yaml` for a
ready-made example.

Schema: [`docs/schemas/config.schema.yaml`](../../schemas/config.schema.yaml).
Machine-wide path defaults: copy [`config.example.yaml`](config.example.yaml) to
`$XDG_CONFIG_HOME/mas/config.yaml` (default: `~/.config/mas/config.yaml`).

### 3 — Build images

```bash
cd docker
docker compose build backend   # CLI + controller API
# UI (optional): docker compose build ui
```

Tags: `mas-lab-backend:local` (required), `mas-lab-ui:local` (optional UI). First backend build takes several minutes.

Clean rebuild (remove old images first):

```bash
task docker-rebuild
# or: docker compose down --rmi local && docker rmi mas-lab-backend:local mas-lab-ui:local
#     && docker compose build --no-cache
```

### 4 — Verify the CLI (offline)

These commands confirm that Docker can run `mas-ctl` and read tutorial manifests.
They do **not** call an LLM, so you can run them before adding an API key.

```bash
docker compose -f docker/compose.yaml run --rm --no-deps cli mas-lab config
docker compose -f docker/compose.yaml run --rm --no-deps cli mas-ctl validate \
  docs/tutorials/01-building-an-agent/agent.yaml
```

**Live LLM** (after `OPENAI_API_KEY` is in `docker/.env`; use `gpt-4o-mini` on corporate proxies):

```bash
MAS_CTL_MODEL=gpt-4o-mini docker compose -f docker/compose.yaml run --rm --no-deps cli mas-ctl chat \
  docs/tutorials/01-building-an-agent/agent.yaml \
  -q "What is the capital of France?"
```

**Corporate / OpenAI-compatible proxy** — set `infra_refs: [standard:llm-proxy]` in
`config.yaml` (or `MAS_INFRA_REFS=standard:llm-proxy`) and
`LLM_PROXY_API_BASE` in `.env` / `docker/.env`. See
[`.env.example`](.env.example).

**Offline mock** (no network — uses mock infra overlay from Tutorial 1):

```bash
docker compose -f docker/compose.yaml run --rm --no-deps cli mas-ctl chat \
  docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/mock-llm.yaml \
  -q "What is 2+2?"
```

| CLI | What it does |
|-----|----------------|
| `mas-ctl validate <agent.yaml>` | Schema + refs without running |
| `mas-ctl chat <agent.yaml> -q "…"` | Single agent, one turn |
| `mas-ctl run-mas <mas.yaml> -q "…"` | Full MAS workflow |
| `mas-ctl list-bundles` | Installed infra bundles (`standard:openai`, …) |
| `mas-lab config` | Effective data paths and overrides |

On `mas-ctl`, **`-o` / `--overlay`** applies a manifest overlay (not an output path).
To write the trace elsewhere, use **`--events-file /path/to/events.jsonl`**.

### 5 — Trace cache and finding results

| Store | Default location | Purpose |
|-------|------------------|---------|
| **Trace cache** | `$XDG_CACHE_HOME/mas/traces/` (default `~/.cache/mas/traces/`) | Content-addressed LLM traces — **re-runs skip cached completions** |
| **Lab outputs** | `$XDG_DATA_HOME/mas/labs/<lab>/<experiment>/…` | Benchmark trees: `…/itemN/rN/traces/events.jsonl`, `results/` |
| **CLI chat traces** | Next to manifest: `traces/events.jsonl` unless `--events-file` set | Ad-hoc `mas-ctl chat` runs |

Confirm paths:

```bash
mas-lab config
```

**Override output location**

| Tool | Flag | Effect |
|------|------|--------|
| `mas-lab benchmark run` | `-o` / `--output-dir PATH` | Write this experiment under `PATH` instead of the global labs tree |
| `mas-lab benchmark run` | `--trace-cache PATH` | Separate trace cache (bypass shared cache) |
| `mas-ctl chat` | `--events-file PATH` | Write `events.jsonl` to `PATH` |
| Env | `MAS_LABS_ROOT`, `MAS_TRACE_CACHE`, `MAS_RUNS_ROOT` | Override globals (see `mas-lab config`) |

Workspace `paths:` keys in `config.yaml` mirror `$XDG_CONFIG_HOME/mas/config.yaml`
when you want per-project defaults (schema: `paths.labs_dir`, `paths.cache_dir`,
`paths.runs_dir`).

### 6 — Start the web UI

The browser UI is the easiest way to browse manifests and benchmark results after
install. It uses the same Docker stack as the CLI.

```bash
cd docker && docker compose up -d
# or from repo root: task start
```

| Service | URL |
|---------|-----|
| **Web UI** | http://localhost:8080 |
| Controller API | http://localhost:8090/api/health |

What to try: open an experiment under `labs/` or `docs/tutorials/`, validate it,
and inspect `results/` from a completed run. Guide: [Web UI](../../ui/index.md).

### 7 — Next

→ [Tutorial 1 — Building an Agent](../01-building-an-agent/) — prefix commands with
`docker compose -f docker/compose.yaml run --rm --no-deps cli` when staying on Docker.

---

## Path A — Docker users

Everything in the [fast path](#fast-path-docker-only), plus how mounts and config work.

### Volume mounts

| Container | Host (default) | Purpose |
|-----------|----------------|---------|
| `/workspace` | Repository root (`..` from `docker/`) | `labs/`, `infra/`, tutorials |
| `/data` | `docker/data/` | Trace cache, benchmark outputs |

Override in `docker/.env`:

```bash
MAS_WORKSPACE_MOUNT=/path/to/your/project
MAS_DATA_MOUNT=/path/to/persistent-data
```

The sample workspace file is at [`examples/sample-workspace/config.yaml`](../../../examples/sample-workspace/config.yaml).
Copy it to your project root as `config.yaml`, or set
`MAS_WORKSPACE_ROOT=examples/sample-workspace` when working from this checkout.

### Configuration priority (inside Docker)

```
/workspace/config.yaml   ← project copy (highest; optional on host mount)
/opt/mas-lab/config.yaml ← baked sample when mount has no project file
docker/.env                     ← OPENAI_API_KEY
/data/                            ← trace cache & benchmark outputs
```

`MAS_WORKSPACE_ROOT=/workspace` is set in the container. The runtime does **not**
read a host `$XDG_CONFIG_HOME/mas/config.yaml` when that env var is set.

### One-off CLI commands

```bash
cd docker

# Benchmark (uses trace cache under /data)
docker compose run --rm cli mas-lab benchmark run \
  labs/design-space.lab/01-design-patterns/experiment.yaml --dry-run

# Multi-agent
docker compose run --rm cli mas-ctl run-mas path/to/mas.yaml -q "Hello"
```

The `cli` service uses the **tools** profile — it is the service for one-off CLI commands (`docker compose --profile tools run --rm cli …`). Don't use `backend` (the long-running API service) for CLI commands.

### Taskfile helpers (optional)

Install [go-task](https://taskfile.dev/), then from the **repository root**:

| Task | Purpose |
|------|---------|
| `task start` | Build if needed, start UI + backend detached |
| `task restart` | Rebuild + recreate after `docker/.env` or code changes |
| `task verify-env` | Confirm `OPENAI_API_KEY` inside the running backend container |
| `task docker-rebuild` | Remove local images and `docker compose build --no-cache` |

Secrets belong in `docker/.env` only — shell `export OPENAI_API_KEY` is **not**
passed into containers (avoids stale keys). After editing `.env`, run `task restart`.

Full reference: `docker/README.md` in the repository.

---

## Path B — Developers (uv + task)

Use this path when you change Python sources in `runtime/`, `ctl/`, or `lab/`.

### 1 — Prerequisites (one-time)

| Tool | Purpose | Install |
|------|---------|---------|
| **Python ≥ 3.11** | Runtime | `python3 --version` |
| **uv** | Fast installs | `brew install uv` or [astral.sh/uv](https://astral.sh/uv/) |
| **task** | Repo automation | `brew install go-task` |
| **direnv** (recommended) | Auto-activate `.venv` | `brew install direnv` + hook in `~/.zshrc` |

### 2 — Clone and install

```bash
git clone https://github.com/outshift-open/mas-lab.git
cd mas-lab
direnv allow          # optional; uses committed .envrc → ./.venv
task install          # editable: runtime, ctl, library-standard, lab stack
```

Verify CLIs:

```bash
command -v mas-lab mas-ctl mas-runtime
mas-lab --help
```

For evaluation metrics, tutorials, and sample apps:

```bash
task install-dev      # install + pytest, pyarrow, library-samples
# or full optional libraries:
task install-all
```

Manifest reference: [references/index.md](../../references/index.md).

### 3 — direnv and `.env`

The committed `.envrc` sets `UV_PROJECT_ENVIRONMENT=./.venv` so this checkout
never shadows another project's venv.

Create a **gitignored** `.env` at the repo root for secrets:

```bash
cat > .env <<'EOF'
OPENAI_API_KEY=sk-...
EOF
```

`mas-lab benchmark run` and `mas-ctl chat` walk up from the cwd and load `.env`
automatically. **Never** commit API keys.

### 4 — Environment overrides (no YAML edits)

| Variable | Purpose |
|----------|---------|
| `MAS_INFRA_REFS` | Replace `infra_refs` from `config.yaml` (e.g. `standard:llm-proxy`) |
| `MAS_CTL_MODEL` | Override the agent model for one run (e.g. `gpt-4o-mini`, or a provider-prefixed id via a proxy gateway) |
| `MAS_LLM_MODEL` | Alias for `MAS_CTL_MODEL` (legacy `.env` name) |
| `MAS_WORKSPACE_ROOT` | Point at a project root when cwd is elsewhere |
| `LLM_PROXY_API_BASE` | API base for `standard:llm-proxy` (read from `.env`) |
| `OPENAI_API_KEY` | Credential named by the LLMProxy manifest |

Example (proxy gateway, Tutorial 0 CI smoke):

```bash
export MAS_INFRA_REFS=standard:llm-proxy
export MAS_CTL_MODEL=gpt-4o-mini
export OPENAI_API_KEY=...
export LLM_PROXY_API_BASE=https://your-proxy.example/v1
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -q "What is the capital of France?"
```

### 5 — User config (`$XDG_CONFIG_HOME/mas/config.yaml`)

Machine-wide paths and default infra bundle:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/mas"
cp docs/tutorials/00-environment-setup/config.example.yaml \
  "${XDG_CONFIG_HOME:-$HOME/.config}/mas/config.yaml"
```

Or create manually:

```yaml
apiVersion: mas.config/v1
kind: UserConfig
default_infra: standard:production
runs_dir: ~/.local/share/mas/runs
cache_dir: ~/.cache/mas
labs_dir: ~/.local/share/mas/labs
```

Check effective paths:

```bash
mas-lab config
```

### 6 — Taskfile overview

Run `task --list` from the repo root. Common tasks:

| Task | Purpose |
|------|---------|
| `task install` / `install-dev` / `install-all` | Editable package installs |
| `task verify` | Pre-commit gate (unit + tutorial manifests + smoke) |
| `task verify-tutorials` | Replay tutorial `demo/scenario.yaml` commands |
| `task reproduce` | Run all paper lab experiments |
| `task start` / `restart` | Docker UI stack |
| `task docs-serve` | Local MkDocs site (`http://127.0.0.1:8000`) |
| `task docs-build` | Build site to `site/` (same as GitHub Pages CI) |

### 7 — Smoke test

```bash
mas-ctl validate docs/tutorials/01-building-an-agent/agent.yaml
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -q "What is the capital of France?"
```

Offline (no network):

```bash
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/mock-llm.yaml \
  -q "What is 2+2?"
```

### 7 — Keeping up to date

```bash
git pull
task install      # only if pyproject.toml dependencies changed
```

Editable installs pick up **code** changes immediately; dependency changes need `task install`.

---

## Infrastructure: LLM endpoints and data paths

The runtime needs a non-secret **infra reference** (where to call the LLM) and a
secret **API key** in `.env` or `docker/.env`.

### OSS infra bundles (`library-standard`)

| Bundle | Use when |
|--------|----------|
| `standard:openai` | OpenAI API (`OPENAI_API_KEY`) |
| `standard:ollama` | Local Ollama at `http://localhost:11434/v1` (no key) |
| `standard:production` | **Default for tutorials** — wraps `standard:openai` |
| `standard:development` | Local Ollama bundle |

List installed bundles:

```bash
mas-ctl list-bundles
# Docker:
docker compose -f docker/compose.yaml run --rm --no-deps cli mas-ctl list-bundles
```

Set the default in `$XDG_CONFIG_HOME/mas/config.yaml` (`default_infra: standard:production`) or
per-project in `config.yaml` (`infra_refs:`). CLI `--infra-ref` overrides
for one run.

### Inline URL (quickest smoke test)

```bash
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  --infra-ref http://localhost:11434/v1 -q "Hello"
```

### Data directories

| Setting | Contents |
|---------|----------|
| `labs_dir` | Experiment trees (`<name>/<scenario>/itemN/rN/traces/events.jsonl`) |
| `cache_dir/traces/` | Content-addressed trace store |
| `cache_dir/artifacts/` | Pipeline step cache |

Override: `MAS_LABS_ROOT`, `MAS_TRACE_CACHE`, or fields in `$XDG_CONFIG_HOME/mas/config.yaml`.
Always confirm with `mas-lab config`.

More detail: [user-config.md](../../user-config.md).

---

## Verify this tutorial (CI)

**Developer path (no Docker):**

```bash
pytest tests/tutorials/test_scenario_commands.py -v -k "tuto-00 and Developer"
```

**Docker path** (skipped automatically when the daemon is not running):

```bash
pytest tests/tutorials/test_scenario_commands.py -v -k tuto-00
```

Full tutorial gate: `task verify-tutorials`.

**Live LLM** (requires `OPENAI_API_KEY` in `.env` or `docker/.env`):

```bash
TUTORIAL_ONLINE=1 pytest tests/tutorials/test_scenario_commands.py -v -k tuto-00
```

---

## Common errors

### `command not found: mas-lab`

Activate the venv: `direnv allow` or `source .venv/bin/activate`, then `task install`.

### `401` from the LLM

- Docker: set `OPENAI_API_KEY` in `docker/.env`, then `task restart`
- Source: set `OPENAI_API_KEY` in repo `.env` or `source .env`
- Check bundle: `mas-lab config` and `default_infra` in `$XDG_CONFIG_HOME/mas/config.yaml`

### Docker build fails

Ensure you run `docker compose` from `docker/` (or use `docker compose -f docker/compose.yaml` from repo root). Network is required for the first `uv sync` inside the image.

### Wrong benchmark output path

Run `mas-lab config` — outputs go to `$XDG_DATA_HOME/mas/labs/` by default (or paths from user config).

---

## Next

→ [Tutorial 1 — Building an Agent](../01-building-an-agent/)
