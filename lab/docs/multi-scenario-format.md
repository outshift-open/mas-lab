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

On disk, the directory tree *is* the artifact tree — each level (`application` /
`scenario` / `test` / `run`) owns whatever artifacts it declares in its own
`artifacts:` block:

```text
<output_dir>/
  data.csv                              # application-level artifact (e.g. gathered df)
  <scenario-id>/
    data.csv                            # scenario-level artifact
    item<N>/
      data.csv                          # test-level artifact
      r<R>/
        traces/events.jsonl             # run-level artifact (trace)
        metrics.json                    # run-level artifact (eval_mce output)
        data.csv                        # run-level artifact (metrics_to_dataframe output)
```

A `gather_level` step placed at `test:`/`scenario:`/`application:` fans the
level below's named artifact upward (see [pipeline-steps.md](pipeline-steps.md)
and the `in:`/`out:`/`scope:` fields in
[manifests/pipeline.md](../../docs/manifests/pipeline.md)).

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

Each level (`run:`/`test:`/`scenario:`/`application:`) can declare its own
`artifacts:` and `post:` steps. A step's `scope` is inferred from which level
block it's declared under:

```yaml
  run:
    artifacts:
      trace: { type: trace, path: "{run_dir}/traces/events.jsonl" }
      metrics: metrics
    post:
      - name: eval-quality
        type: eval_mce
        in: trace
        out: metrics

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
