<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Multi-scenario experiment format

How an **experiment manifest** combines **scenarios**, a **dataset**, and **runs**.

Terms: [glossary.md](../../docs/glossary.md). Schema:
[manifests/experiment.md](../../docs/manifests/experiment.md).

## Execution grid

```text
for scenario in scenarios:
  for item in dataset:
    for run_index in 1..n_runs:
      execute (scenario overlays × item)
```

On disk:

```text
<output_dir>/
  <scenario-id>/item<N>/r<R>/traces/events.jsonl
  results/          # pipeline outputs (all scenarios)
```

## `scenarios:`

```yaml
experiment:
  scenarios:
    - id: linear
      overlays:
        logic: [linear]
        control: []
        infra: []
      tags: [topology]
    - id: moderator
      overlays:
        logic: [moderator-broker]
        control: []
        infra: []
```

| Field | Meaning |
|-------|---------|
| `id` | Folder name and table key |
| `overlays` | Layered stacks (`logic`, `control`, `infra`) from `configs_dir` |
| `tags` | Filter in CLI (`--limit-scenarios`, …) |

## `dataset:`

```yaml
  dataset:
    path: ./datasets/queries.yaml
```

Format: [dataset.md](../../docs/manifests/dataset.md).

## MAS binding

```yaml
  applications:
    - app: trip-planner
      configs_dir: ./overlays
```

Or explicit manifest:

```yaml
  applications:
    - manifest: ./mas.yaml
      configs_dir: ./overlays
```

## Post-run pipeline

```yaml
  application:
    post:
      - name: extract-trace-stats
        type: extract_trace_stats
        config:
          output: "{output_dir}/results/trace_stats.csv"
```

Step types: [pipeline-steps.md](pipeline-steps.md).

## Example

[design-space.lab/02-topologies/experiment.yaml](../../labs/design-space.lab/02-topologies/experiment.yaml).
