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

**Writing YAML:** [How to write manifests](writing-manifests.md) — inline vs
file vs catalog id, `LIBRARY:` prefix, `name@version`, and file-name
conventions (`mas.yaml`, `*.tool.yaml`, `experiment.yaml`, …).

---

## How manifests fit together

```text
experiment.yaml          ← what to run (scenarios × dataset × n_runs + pipelines)
    │
    ├── applications[]   → mas.yaml / registered app
    ├── scenarios[]    → overlay stacks per variant
    ├── dataset        → prompts, turns, memory seeds
    └── post: / scenario.post / item.post / run.post  → pipeline steps (metrics, plots)

mas.yaml                 ← team topology, workflow, transport
    └── agents/*.yaml    ← design pattern, tools, skills, observability

config.yaml       ← project defaults — [reference](../references/config.yaml.md)
```

| Layer | Manifest kinds | Reference |
|-------|----------------|-----------|
| **Agent** | `Agent`, `Tool` | [agent.md](agent.md) · [plugin-bindings.md](plugin-bindings.md) · [context-assembly.md](context-assembly.md) · [summarization.md](summarization.md) · [tool.md](tool.md) |
| **Runtime engine** | `RuntimeEngine` (`infra/v1`, via workspace / CLI) | [runtime-engine.md](runtime-engine.md) · [execution.md](execution.md) (migration) |
| **MAS** | `MAS`, `Workflow` | [mas.md](mas.md), [workflow.md](workflow.md) |
| **Override** | `Overlay` | [overlay.md](overlay.md) |
| **Environment** | `Flavour`, `InfraBundle`, `LLMProxy`, `InfraMiddleware`, `ToolServerRegistry` | [flavour.md](flavour.md), [infra.md](infra.md), [llm-cache.md](llm-cache.md) · [ref](../references/llm-cache.md), [ToolServerRegistry](../references/tool-server-registry.md) |
| **Experiment** | `experiment:` | [experiment.md](experiment.md) — `models` slot map (`main` / `summarizer` / `judge`) |
| **Inputs** | `Dataset` | [dataset.md](dataset.md) |
| **Processing** | `pipeline:` / `kind: Pipeline` | [pipeline.md](pipeline.md) |
| **Interactive demo** | `lab:` | [lab.md](lab.md) |
| **Library** | `kind: Library` (`library.yaml`) | [labs-and-libraries.md](../labs-and-libraries.md) |

Runtime execution manifests (`Agent`, `MAS`, overlays, infra) are documented under
[runtime.md](runtime.md).

---

## Resolution: inline vs file vs id

See [writing-manifests.md](writing-manifests.md) for the full convention.
Short form:

| Form | Example | Meaning |
|------|---------|---------|
| **Inline object** | `design_pattern: { type: react }` | Embedded in the parent YAML |
| **File path** | `ref: ./agents/broker.yaml` | Relative, absolute, or `library:path` |
| **Catalog id** | `app: library-ioc:sre-triage@v2` | `[library:]name@version` for versioned families |
| **Library path** | `samples:apps/trip-planner/mas.yaml` | Slash after `LIBRARY:` is a path, not an id |
| **CLI override** | `--infra-ref`, `-o overlay.yaml` | One-shot for `mas-ctl` |

Do not write `../../apps/foo/mas.yaml`. Do not use `sre-triage-v2` or
`sre-triage/v2` as catalog ids.

---

## Schema files

YAML schemas live under [`docs/schemas/`](../schemas/). The bench UI and
`mas-ctl validate` compile them at runtime.

| Area | Schema directory |
|------|------------------|
| Lab (experiment, dataset, pipeline) | `docs/schemas/lab/` |
| Runtime (agent, mas, overlay, infra) | `docs/schemas/runtime/` |
| Workspace | [config.schema.yaml](../schemas/config.schema.yaml) |

---

## Application binding (tutorials vs paper labs)

Both forms are valid in `experiment.applications[]`:

| Style | Example | When to use |
| --- | --- | --- |
| **Inline / local file** | `manifest: ./agent.yaml` + optional `configs_dir` | Tutorials, self-contained experiments |
| **Registered app** | `app: library-ioc:sre-triage@v2` | Shared apps; prefer this over `../../apps/...` |

Scenarios reference overlay **ids** from `configs_dir`. Dataset: `path: ./dataset.yaml` (tutorial) or `name` + optional `locator` (catalogued benchmarks).

See [topology-and-workflow.md](topology-and-workflow.md) for workflow vs routing overlays.

---

## See also

- [labs-and-libraries.md](../labs-and-libraries.md) — lab vs library vs local plugin
- [user-config.md](../user-config.md) — XDG paths
- [config.yaml reference](../references/config.yaml.md) — workspace YAML fields
- [cli/index.md](../cli/index.md) — CLIs
- [cli/mas-ctl.md](../cli/mas-ctl.md) — `mas-ctl` flags
- [cli/observability.md](../cli/observability.md) — `events.jsonl`
- [paper/index.md](../paper/index.md) — sample labs that ship with the repo
