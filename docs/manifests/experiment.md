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

## See also

- [lab.md](lab.md)
- [pipeline.md](pipeline.md)
- [Tutorial 03](../tutorials/03-experiments-and-analysis/README.md)
- [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md)
