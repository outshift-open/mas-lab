<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Manifest reference

MAS Lab is configured through YAML **manifests**: declarative files for agents,
multi-agent systems, experiments, datasets, overlays, and pipelines.

**New to the vocabulary?** Read [glossary.md](../glossary.md) first (scenario,
overlay, pipeline, run, flavour).

**Hands-on:** start with [Tutorial 1](../tutorials/01-building-an-agent/README.md)
(agent) → [Tutorial 2](../tutorials/02-creating-a-mas/README.md) (MAS) →
[Tutorial 3](../tutorials/03-experiments-and-analysis/README.md) (experiments).

---

## How manifests fit together

```text
experiment.yaml          ← what to run (scenarios × dataset × n_runs + pipelines)
    │
    ├── applications[]   → mas.yaml / registered app
    ├── scenarios[]    → overlay stacks per variant
    ├── dataset        → prompts, turns, memory seeds
    └── application.post / scenario.post / …  → pipeline steps (metrics, plots)

mas.yaml                 ← team topology, workflow, transport
    └── agents/*.yaml    ← design pattern, tools, skills, observability

mas-workspace.yaml       ← project defaults (flavour, infra_refs, .env path)
```

| Layer | Manifest kinds | Reference |
|-------|----------------|-----------|
| **Agent** | `Agent` | [agent.md](agent.md) |
| **MAS** | `MAS`, `Workflow` | [mas.md](mas.md), [workflow.md](workflow.md) |
| **Override** | `Overlay` | [overlay.md](overlay.md) |
| **Environment** | `Flavour`, `InfraBundle`, `LLMProxy` | [flavour.md](flavour.md), [infra.md](infra.md) |
| **Experiment** | `experiment:` | [experiment.md](experiment.md) |
| **Inputs** | `Dataset` | [dataset.md](dataset.md) |
| **Processing** | `pipeline:` / `kind: Pipeline` | [pipeline.md](pipeline.md) |
| **Interactive demo** | `lab:` | [lab.md](lab.md) |

Runtime execution manifests (`Agent`, `MAS`, overlays, infra) are documented under
[runtime.md](runtime.md).

---

## Resolution: `ref` vs `id`

| Form | Example | Meaning |
|------|---------|---------|
| **File path** | `ref: ./agents/broker.yaml` | Relative to the referring manifest |
| **Catalog name** | `dataset.name: arborian-network` | Resolved under the lab or library |
| **Library ref** | `standard:openai` | Bundled infra from `library-standard` |
| **CLI override** | `--infra-ref`, `-o overlay.yaml` | One-shot for `mas-ctl` |

---

## Schema files

YAML schemas live under [`docs/schemas/`](../schemas/). The bench UI and
`mas-ctl validate` compile them at runtime.

| Area | Schema directory |
|------|------------------|
| Lab (experiment, dataset, pipeline) | `docs/schemas/lab/` |
| Runtime (agent, mas, overlay, infra) | `docs/schemas/runtime/` |
| Workspace | [mas-workspace.schema.yaml](../schemas/mas-workspace.schema.yaml) |

---

## Application binding (tutorials vs paper labs)

Both forms are valid in `experiment.applications[]`:

| Style | Example | When to use |
| --- | --- | --- |
| **Inline manifest** | `manifest: ./agent.yaml` + optional `configs_dir` | Tutorials, self-contained experiments |
| **Registered app** | `app: trip-planner` + `configs_dir: overlays/` | Paper labs, shared apps under `library-samples/apps/` |

Scenarios reference overlay **ids** from `configs_dir` (e.g. tutorial `cot` vs lab `pattern-cot`). Dataset: `path: ./dataset.yaml` (tutorial) or `name` + `locator: samples` (catalogued benchmarks).

See [topology-and-workflow.md](topology-and-workflow.md) for workflow vs routing overlays.

---

## See also

- [user-config.md](../user-config.md) — `~/.mas/config.yaml` and `mas-workspace.yaml`
- [cli/observability.md](../cli/observability.md) — `events.jsonl` and CLI flags
- [paper/index.md](../paper/index.md) — sample labs that ship with the repo
