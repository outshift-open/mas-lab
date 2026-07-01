<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# MAS Lab packages

MAS Lab ships as a small set of installable Python packages. Most users interact
with the **CLIs**; extension authors add plugins, pipeline steps, or libraries on
top of the same contracts.

Install everything from a repository checkout with:

```bash
uv sync --all-packages
```

Requires **Python 3.11+**.

---

## How the pieces fit together

| Layer | Package | What it does |
|-------|---------|--------------|
| **Runtime** | `mas-runtime` | Executes agents and teams from YAML manifests — contracts, plugins, traces |
| **Control plane** | `mas-ctl` | Chat, validate, compose, and run multi-agent workflows (`run-mas`) |
| **Lab** | `mas-lab` | Benchmark experiments, pipelines, reports, and the web UI controller |
| **Standard library** | `mas-library-standard` | Flavours, overlays, infra bundles, and built-in runtime plugins |
| **Samples** | `mas-library-samples` | Reference apps (e.g. trip planner), datasets, and tutorial fixtures |

**Typical path:** [Tutorial 0](tutorials/00-environment-setup/README.md) →
`mas-ctl` for agents and teams → `mas-lab benchmark run` for experiments.

Supporting packages (`mas-library-lab`, `mas-library-eval`, and the `mas-lab`
component libraries) provide shared types, evaluation metrics, and UI/backend
code. They are installed automatically when you depend on `mas-lab`; you rarely
import them directly unless you are extending the toolkit.

---

## Package reference

| Package | Directory | CLI | Role |
|---------|-----------|-----|------|
| `mas-runtime` | `runtime/` | `mas-runtime` | Headless agent execution (CI, containers) |
| `mas-ctl` | `ctl/` | `mas-ctl` | Interactive and scripted orchestration |
| `mas-lab` | `lab/` | `mas-lab` | Benchmarks, pipelines, controller API |
| `mas-library-standard` | `library-standard/` | — | Standard plugins, flavours, observability sinks |
| `mas-library-samples` | `library-samples/` | — | Sample MAS apps and benchmark datasets |
| `mas-library-lab` | `library-lab/` | — | Lab extension plugins (eval providers, helpers) |
| `mas-library-eval` | `library-eval/` | — | Session-level evaluation metrics for benchmarks |

Published from PyPI (when available): `uv pip install mas-lab` pulls the runtime,
control plane, and lab stack transitively.

---

## Where to read more

| Goal | Start here |
|------|------------|
| First install | [Tutorial 0](tutorials/00-environment-setup/README.md) |
| Day-to-day use | [User guide](user-guide.md) |
| YAML manifests | [References](references/index.md) |
| Paper reproduction | [Paper labs](paper/index.md) |
| Runtime development | [`runtime/docs/`](../runtime/docs/index.md) in the repository |
| Control plane | [`ctl/docs/`](../ctl/docs/user-guide.md) in the repository |

Site: [outshift-open.github.io/mas-lab](https://outshift-open.github.io/mas-lab/)

---

## Schemas

Workspace configuration: [config.schema.yaml](schemas/config.schema.yaml).

Experiment and benchmark manifests are validated by `mas-lab validate` against
schemas under `lab/components/bench/src/mas/lab/manifests/schema/`. Manifest
field reference: [References](references/index.md).

---

## Extending MAS Lab

| Area | Extend | Entry points |
|------|--------|--------------|
| **Agent runtime** | Design patterns, tools, overlays, observability | Runtime plugin registry — see [`runtime/docs/`](../runtime/docs/index.md) |
| **Benchmark pipelines** | Custom step types (metrics, plots, reports) | Pipeline `type:` in `experiment.yaml` — see [lab manifests](manifests/pipeline.md) |
| **Evaluation** | Session-level judges and metrics | `mas-library-eval` / MCE integration — see [Tutorial 3](tutorials/03-experiments-and-analysis/README.md) |
| **Deployment** | Controller backends for the lab UI | `mas.lab.controller.plugins` entry-point group |

For local development, use editable installs only when you are patching packages
in this repository:

```bash
uv pip install -e runtime -e ctl -e lab -e library-standard -e library-lab -e library-eval
```

---

## Related

- [User guide](user-guide.md)
- [User configuration](user-config.md)
- [Glossary](glossary.md)
