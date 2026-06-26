<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-ctl

> Multi-agent orchestration — compose, chat, validate, run.

---

## Objective

`mas-ctl` manages multi-agent systems described by declarative **MAS manifests**
(`mas.yaml`). It resolves topologies, applies flavours and infra bundles, runs
workflows, and provides the **interactive** CLI (`chat`, `tui`) on top of
`mas-runtime`.

```
mas-runtime  ←  single agent : kernel + contracts + design-pattern plugins
mas-ctl      ←  multi-agent  : compose, chat, run-mas, validate
mas-lab      ←  evaluation   : benchmarks, pipelines, controller UI
```

Benchmarking is **`mas-lab`**, not `mas-ctl`.

---

## Install

```bash
uv sync --package mas-ctl
# or full workspace
uv sync --all-packages
```

---

## Quickstart

```bash
# Validate manifests
mas-ctl validate agent.yaml
mas-ctl validate mas.yaml

# Interactive single agent
mas-ctl chat agent.yaml -q "Hello"

# Run a MAS
mas-ctl run-mas library-samples/apps/trip-planner/mas.yaml --flavour local

# Inspect workspace / infra
mas-ctl infra list
mas-ctl flavour list
```

---

## Key concepts

### MAS manifest (`mas.yaml`)

Declares agents, workflow, and metadata. See
[docs/manifests/mas.md](../docs/manifests/mas.md).

### Flavour

Selects model endpoint and non-secret configuration (`local`, `mock`, …) from
`library-standard`.

### Scenario

Named overlay for A/B configuration without duplicating manifests.

### Workspace

`~/.mas/config.yaml` and optional `mas-workspace.yaml` — see
[docs/user-config.md](../docs/user-config.md).

---

## CLI reference

| Command | What it does |
|---------|-------------|
| `mas-ctl chat MANIFEST` | Interactive or scripted conversation |
| `mas-ctl tui MANIFEST` | Terminal UI for chat |
| `mas-ctl run-mas MANIFEST` | Run a multi-agent workflow |
| `mas-ctl compose …` | Compose effective manifests / placement |
| `mas-ctl plan …` | Dry-run placement plan |
| `mas-ctl validate PATH …` | Validate agent / MAS / experiment YAML |
| `mas-ctl schemas` | List JSON/YAML schemas |
| `mas-ctl flavour list\|show` | List or show flavours |
| `mas-ctl infra list\|show` | List or show infra bundles |
| `mas-ctl registry …` | Plugin registry introspection |
| `mas-ctl checkpoint …` | Session checkpoint utilities |
| `mas-ctl list-bundles` | List library bundles |

Full flag reference: [docs/dev/cli/cli-reference.md](../runtime/docs/dev/cli/cli-reference.md)
(runtime doc tree; shared CLI patterns).

---

## Design philosophy

1. **Declarative over imperative** — topology and policies in YAML.
2. **Secrets separated from config** — only `*_env` names in manifests.
3. **Thin CLI** — click handlers call library code in `mas.ctl.*`.
4. **Library-first bench** — `mas-lab` imports ctl session/bootstrap, not subprocesses.

---

## Tutorials

Primary path (MkDocs): **[docs/tutorials/index.md](../docs/tutorials/index.md)**

| # | Tutorial | Topic |
|---|----------|-------|
| 0 | [Environment](../docs/tutorials/00-environment-setup/README.md) | Docker / `uv`, credentials, workspace |
| 1 | [Building an agent](../docs/tutorials/01-building-an-agent/README.md) | `mas-ctl chat`, overlays |
| 2 | [Creating a MAS](../docs/tutorials/02-creating-a-mas/README.md) | `mas.yaml`, `run-mas` |
| 3 | [Experiments](../docs/tutorials/03-experiments-and-analysis/README.md) | `mas-lab benchmark run` |

---

## Examples

| Path | Description |
|------|-------------|
| [library-samples/apps/](../library-samples/apps/) | Trip planner, Q&A, moderator variants |
| [docs/tutorials/](../docs/tutorials/) | Copy-paste tutorial manifests |

Flavours ship in **`library-standard`** and resolve by name:
`mas-ctl run-mas … --flavour local`.

---

## Documentation

| Document | Covers |
|----------|--------|
| [docs/user-guide.md](docs/user-guide.md) | Operational guide |
| [docs/developer-guide.md](docs/developer-guide.md) | Manifest and compose extensions |
| [docs/architecture-v2-compose.md](docs/architecture-v2-compose.md) | Compose pipeline |
| [../docs/manifests/](../docs/manifests/README.md) | YAML reference |
| [../docs/libraries.md](../docs/libraries.md) | Package matrix |
| [../docs/cli/observability.md](../docs/cli/observability.md) | Trace emission and event artifacts |

---

## Related packages

| Package | Role |
|---------|------|
| [`mas-runtime`](../runtime/) | Kernel, contracts, design patterns |
| [`mas-lab`](../lab/) | Benchmarks, pipelines, UI |
| [`library-standard`](../library-standard/) | Flavours, overlays, infra |
