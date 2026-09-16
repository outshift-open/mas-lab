<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# User guide

How to install and use MAS Lab: single agents, multi-agent teams, batch
experiments, and optional libraries.

MAS Lab is a **specification-driven** toolkit. You declare agents and experiments
in YAML, run them with `mas-ctl` and `mas-lab`, and analyze results through
reusable benchmark pipelines.

**Related:** [References](references/index.md) · [Web UI](ui/index.md) ·
[Run logs](cli/observability.md) · [Paper labs](paper/index.md) · [Glossary](glossary.md)

---

## Ways to work with MAS Lab

Several entry points fit different goals. All of them need a working environment first —
complete **[Tutorial 0 — Environment setup](tutorials/00-environment-setup/README.md)** once
(Docker or developer install, LLM credentials). The same setup covers the CLI and the
optional web UI.

### Hands-on tutorials

Learn the toolkit step by step: one agent, then a multi-agent team, then a full
benchmark experiment.

| | Tutorial | What you will do |
|---|----------|------------------|
| 0 | [Environment setup](tutorials/00-environment-setup/README.md) | Install and verify your environment |
| 1 | [Build an agent](tutorials/01-building-an-agent/README.md) | Author a manifest and chat with your agent |
| 2 | [Orchestrate your MAS](tutorials/02-creating-a-mas/README.md) | Define a team and run it end to end |
| 3 | [Run an experiment](tutorials/03-experiments-and-analysis/README.md) | Run a benchmark and inspect results |

[Tutorials index](tutorials/index.md)

### Paper labs

Reproduce the experiments from the MAS-Lab article — three labs under `labs/` that
match Section 5 of the paper.

[Paper labs & reproducibility](paper/index.md)

### Web UI

Design agents and experiments, browse manifests, and inspect benchmark runs in the
browser. Started as part of Tutorial 0 (same Docker stack).

[Web UI guide](ui/index.md)

---

## Three CLIs

| CLI | Package | Use for |
|-----|---------|---------|
| `mas-ctl` | `ctl/` | Chat, TUI, compose, validate, `run-mas` |
| `mas-runtime` | `runtime/` | Headless `run-agent` (Docker / CI) |
| `mas-lab` | `lab/` | Benchmarks, pipelines, controller UI |

Benchmarking is always **`mas-lab`**, not `mas-ctl`.

---

## Included libraries

- `mas-runtime`
- `mas-lab`
- `mas-ctl`
- `mas-library-standard`
- `mas-library-lab`

Full package map: [libraries.md](libraries.md).

---

## Install

### Docker (recommended for new users)

```bash
git clone https://github.com/outshift-open/mas-lab.git && cd mas-lab
cd docker && cp .env.example .env
# Edit .env and set OPENAI_API_KEY if you plan to call a live model
docker compose build backend
```

Then follow [Tutorial 0](tutorials/00-environment-setup/README.md) for workspace
setup and your first `mas-ctl` commands.

Mount your project at `/workspace` and persistent data at `/data` via
`MAS_WORKSPACE_MOUNT` and `MAS_DATA_MOUNT` in `docker/.env`.
See `docker/README.md` in the repository.

**Start the web UI** (same compose stack):

```bash
docker compose up --build
# UI http://localhost:8080 · API http://localhost:8090
```

See [Web UI](ui/index.md) for what you can do in the browser.

### From source (developers)

Recommended consumption model:

1. Install versioned OSS packages normally.
2. Use packaged sample apps through their canonical `pkg://` URIs.
3. Only switch to editable multi-package development when you are modifying the OSS code itself.

Typical install from a development checkout:

```bash
uv sync --all-packages

# Optional but recommended: avoid prefixing every command with `uv run`
export PATH="$PWD/.venv/bin:$PATH"

# Verify command resolution
mas-runtime --help >/dev/null
mas-ctl --help >/dev/null
mas-lab --help >/dev/null
```

Editable installs per package when developing:

```bash
uv pip install -e runtime -e lab -e ctl -e library-standard -e library-lab
```

Typical install from a package index:

```bash
uv pip install mas-lab
```

---

## Sample apps

Canonical sample app references:

- `app: trip-planner` — resolves `mas.yaml` via `mas.apps` (from `mas-library-samples`)
- `samples:apps/trip-planner/mas.yaml` — manifest library scheme ref

When you work from a source checkout, relative paths under `library-samples/` or
tutorial directories also work. Prefer `app:` or library scheme refs in
committed labs so paths stay stable across machines.

---

## Typical workflow

1. Build or run an agent with runtime.
2. Orchestrate multi-agent setup with ctl.
3. Run experiments with lab.
4. Add standard/library-lab extensions as needed.

---

## Referencing apps from labs

When a lab needs to run an app, use one of these three patterns.

### 1. Library app via `app:` or `samples:` scheme (recommended)

```yaml
mas:
  app: trip-planner
  base_scenario: baseline
```

Or an explicit manifest library path:

```yaml
applications:
  - manifest: samples:apps/trip-planner/mas.yaml
```

### 2. Absolute path inside the current workspace

Use for local development when the app lives in the same checkout but is not
packaged yet.

### 3. Symlink through a local library-like folder

Use only for local composition — not for committed OSS labs.

For committed reusable OSS examples, prefer `app:` or `samples:` scheme refs.

---

## Running agents with observability

Use **`mas-ctl chat`** for single-agent runs:

```bash
mas-ctl chat my-agent.yaml -q "Your question here" -v
mas-ctl chat my-agent.yaml -q "Your question here" --trace
```

Example from Tutorial 1:

```bash
cd docs/tutorials/01-building-an-agent
mas-ctl chat agent.yaml -o overlays/tools.yaml \
  -q "What is the capital of France?" -v
```

See [cli/observability.md](cli/observability.md) for `events.jsonl` and trace flags.

## Running tools through MCP

MAS Lab supports two tool deployment patterns without changing the agent-facing contract:

- **local provider** — the tool runs in-process
- **MCP provider** — the tool is exposed by a separate MCP server process

The runtime resolves both through the provider registry (tool name → plugin).
`tools: "*"` registers the provider, then queries advertised names at runtime
initialization — verification always passes. An explicit list can be checked
at verification (local names against `spec.tools`).

Serve a MAS tool manifest, then point the agent at that server using
`library-samples/overlays/mcp-localhost.yaml` (not Tutorial 1 overlays):

```bash
mas-mcp serve \
  --tool-manifest library-samples/tools/web-search.tool.yaml \
  --tool web-search \
  --host 127.0.0.1 \
  --port 9001 \
  --transport streamable-http
```

```bash
mcp version
mas-mcp tools list --url http://127.0.0.1:9001/mcp
```

```yaml
providers:
  - name: localhost-mcp-tools
    kind: mcp
    transport: streamable-http
    url: http://127.0.0.1:9001/mcp
    tools: "*"
```

```bash
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/tools.yaml \
  -o library-samples/overlays/mcp-localhost.yaml \
  -o library-samples/overlays/local-in-process.yaml \
  -q "What is the current price of Apple stock?" \
  --trace --trace-summary
```

The `mas-mcp serve` process logs `MCP tool call name=web-search` when the agent
uses the tool. Provider `tools: "*"` is filled at runtime init (discovery),
not at `mas-ctl validate`. Once an external plugin is present, leftover `spec.tools`
(Tutorial 1's `calc`) need `library-samples/overlays/local-in-process.yaml`.
Prod MCP-only setups omit that overlay and must not declare unclaimed tools.

This runs the tool in a dedicated process and exposes it to the MAS runtime via MCP, which is the preferred option when you want infra-owned tooling or a clean separation between the agent process and the tool implementation.

A local tool provider is still the easiest debug path when the tool is part of the same process. The same logical agent interface works in both modes.

See the MCP library docs in [../library-ioa/README.md](../library-ioa/README.md),
[ToolContract](references/tool-contract.md), [kind: Tool](manifests/tool.md), and
infra [`ToolServerRegistry`](references/tool-server-registry.md)
(`library-samples/infra/mcp-localhost.yaml`).

---

## Configuration

Machine-wide paths and workspace defaults: [user-config.md](user-config.md).

Runtime contributor docs live under [`runtime/docs/`](../runtime/docs/index.md)
(Mealy envelope, contracts, design patterns).

The public repository ships tutorials 0–3, three paper labs under `labs/`, and
the v2 Mealy runtime kernel.
