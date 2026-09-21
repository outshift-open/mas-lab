<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Experiment manifest (`experiment:`)

**Package:** `mas-lab-bench` · **Schema:** `experiment.schema.yaml`

An **experiment** manifest tells `mas-lab benchmark run` what to execute: which **MAS** or
**agent**, which **scenarios** (each with **overlays**), which **dataset** items, how many
**runs** per item (`n_runs`), and which **pipeline** steps build `results/` afterward.
Defines **benchmark** metadata, execution modes, lifecycle levels, and **pipeline** hooks.

---

## Four layers

| Level | Scope | Typical pre | Typical post |
|-------|-------|-------------|--------------|
| `application` | Whole experiment | `service_start`, allocate infra | Aggregate metrics, publish report |
| `scenario` | One overlay column | — | Scenario-level plots |
| `test` | One dataset item (all runs) | — | Per-item analysis |
| `run` | Single run index | — | `extract_trajectories`, trace export |

Each level supports `pre:` and `post:` as **lists of pipelines** (0..N).

---

## Core fields

```yaml
experiment:
  name: topology-ablation
  applications:
    - manifest: ./mas.yaml
      configs_dir: ./overlays
  scenarios:
    - id: linear
      overlays:
        logic: [linear]
        control: []
        infra: []
  dataset:
    name: arborian-network
  run:
    n_runs: 5
    pre: []
    post:
      - id: analysis          # library pipeline in lab/pipelines/
  evaluation:
    method: trace_only
```

---

## Pipeline reference forms

| Form | Example |
|------|---------|
| Library id | `{ id: analysis }` or shorthand string in lists |
| File ref | `./pipelines/post-run.yaml` or `{ ref: ... }` |
| Inline steps | `{ steps: [{ name: s1, type: plot_trajectory, ... }] }` |

---

## Artifacts

`artifacts:` declares typed outputs (`trace`, `metrics`, `plot`, …) at experiment
or level scope. Pipeline steps consume/produce these as **typed intermediates** (memory streams
or serialized paths).

---

## Execution (batch orchestration) — legacy shape

> **Planned breaking change (deferred, last in queue):** `experiment.execution` mixes
> **experimental design** (what we compare) with **bench scheduling** (how we walk the
> matrix) and **emulation posture** (replay/trace cache). A future release will
> split these into separate top-level blocks (`experiment.design`, `experiment.schedule`,
> and bench emulation posture). Until then, the key name is historical.

The top-level `experiment.execution` block is **only** for `mas-lab benchmark` batch
runs. It is **not** the removed `spec.execution` field from `kind: Agent` manifests.

| Concern | Where it lives |
| --- | --- |
| LLM endpoints, cache middleware | Workspace `infra_refs`, `MAS_INFRA_REFS`, `--infra-ref`, optional `mas-lab benchmark --infra <name>` (local `infra/<name>.yaml`) |
| Per-turn engine tuning (queue depth, LLM response cache read/write, stream, parallel tools) | `kind: RuntimeEngine` via `runtime_refs` / `--runtime-ref` — see [runtime-engine.md](runtime-engine.md) |
| How many MAS runs run in parallel, timeouts, ordering | `experiment.execution.parallel_scenarios`, `timeout`, `strategy`, … |
| Whole-run trace skip/replay (content-addressed lab cache) | `experiment.execution.emulation.runtime.cache` (`content-addressed` \| `disabled` \| `forced`) |
| Live vs replay for LLM, tools, memory during a benchmark | `experiment.execution.emulation.infra.*` |

Example (smoke run — disable trace cache, keep infra live):

```yaml
experiment:
  name: my-bench
  execution:
    emulation:
      runtime:
        cache: disabled
```

Implementation types: `mas.lab.lab.config.execution` (`MASExecutionSpec`, `EmulationSpec`).

---

## See also

- [lab.md](lab.md)
- [pipeline.md](pipeline.md)
- [Tutorial 03](../tutorials/03-experiments-and-analysis/README.md)
- [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md)
