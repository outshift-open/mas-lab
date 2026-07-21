<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Pipeline step types

Built-in **pipeline step** types for the **embedded pipeline** in
`experiment.yaml`. Labs add more under `lib/steps/`.

How **pipelines** work: [pipeline.md](pipeline.md). **Benchmark** command:
[benchmark.md](benchmark.md). Full OSS catalog: see the [Directory](#directory)
section below, or query it live with the commands there.

## Directory

```bash
mas-lab benchmark pipeline show path/to/experiment.yaml
curl -s http://localhost:8090/api/pipeline-step-types   # when controller running
```

## extract/ — trace → tables

| Type | Output |
|------|--------|
| `extract_trace_stats` | Per-run governance/LLM/tool counts → CSV |
| `extract_mealy_stats` | Per-agent timing → CSV |
| `extract_trajectories` | State sequences |
| `extract_sys_stats` | `sys_stats` events |

## eval/ — scoring & aggregation

| Type | Output |
|------|--------|
| `eval_mce` | MCE evaluation metrics |
| `eval_trip_planner_gt` | Trip-planner ground truth |
| `eval_adversarial` | Adversarial probes |
| `annotate_metrics` | Attach scores to run metadata |
| `collect_metrics` | Aggregate run metrics |
| `compute_ci` | Confidence intervals |

## viz/ — figures

| Type | Output |
|------|--------|
| `plotnine` | Declarative ggplot-style figures |
| `plot` / `ggplot` | Legacy plot steps |
| `plot_trajectory` | Trajectory diagrams |
| `plot_communication_flow` | Agent communication graph |
| `metrics_comparison_plot` | Scenario comparison |
| `ci_plot` | Confidence interval plots |

## data/ — plumbing

| Type | Role |
|------|------|
| `dataset` | Load scenario inputs |
| `experiment` | Run trials (nested pipelines) |
| `collect_dataframe` / `gather_level` | Merge step outputs |
| `join_dataframe` | Join tables |
| `processor` | Custom dataframe transforms |

## services/

| Type | Role |
|------|------|
| `service_start` / `service_stop` | Infra lifecycle |
| `export_otel` | OTel export |

## Internal extensions (mas-lab-internal)

When `mas-lab-bench-steps` is installed: `embed_states`, `list_clickhouse_sessions`.

## Lab-local steps

Paper labs register matplotlib figure steps, e.g.:

- `lib.steps.figure_call_counts:FigureCallCountsStep` (lifecycle-control.lab)

Pattern: subclass `PipelineStep`, `register_step_type`, declare in `experiment.yaml`.

## Related

- [pipeline.md](pipeline.md)
- [benchmark.md](benchmark.md)
