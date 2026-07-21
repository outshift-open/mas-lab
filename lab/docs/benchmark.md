<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Benchmark guide

`mas-lab benchmark` runs an **experiment**: all **scenarios** × **dataset** items ×
**runs**, then the **embedded pipeline** (if declared in `experiment.yaml`).

Full CLI reference: [components/bench/README.md](../components/bench/README.md).
Terms: [glossary.md](../../docs/glossary.md).

## Two phases, one command

| Phase | Command | Produces |
|-------|---------|----------|
| **Execution** | `mas-lab benchmark run experiment.yaml` | Per-**run** `events.jsonl`, `metrics.json` |
| **Pipeline** | Automatic after execution | `results/*.csv`, `results/fig-*.png` |

Re-running skips completed **runs** (unless `--force`) and re-executes **pipeline
steps** when step fingerprints change.

## Essential commands

```bash
mas-lab benchmark run experiment.yaml --progress    # execution + embedded pipeline
mas-lab benchmark run experiment.yaml --dry-run       # JSON Schema validate + execution plan
mas-lab benchmark show last                         # inspect latest output_dir
mas-lab benchmark pipeline run pipeline.yaml -o DIR # pipeline only
```

## Output location

From `experiment.name` and [user-config](../../docs/user-config.md):

- Default (after `mas-lab config`): `$XDG_DATA_HOME/mas/labs/<experiment-name>/`

Override: `-o /path/to/output`.

## Paper reproduction

```bash
task reproduce
```

Per lab: [labs-quickstart.md](labs-quickstart.md).

## More

| Topic | Document |
|-------|----------|
| Pipeline YAML | [pipeline.md](pipeline.md) |
| Pipeline step types | [pipeline-steps.md](pipeline-steps.md) |
| Executor design | [PIPELINE_DESIGN.md](../components/bench/PIPELINE_DESIGN.md) |
| Reproducibility | [Experiments and analysis](../../docs/tutorials/03-experiments-and-analysis/README.md) |
| Paper labs | [paper/index.md](../../docs/paper/index.md) |
