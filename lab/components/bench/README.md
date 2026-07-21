<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-lab-bench

> Reproducible **benchmark** experiments, **pipelines**, and trajectory plots.

`mas-lab-bench` orchestrates **experiments**: **scenarios** × **dataset** items ×
**runs**, then **pipeline steps** on the resulting **`events.jsonl`** logs. Runs
resume from the **trace cache** when inputs match.

**Terms:** [glossary.md](../../../docs/glossary.md) · User guide:
[lab/docs/benchmark.md](../../docs/benchmark.md).

## Pipeline step library

Step *implementations* are library plugins registered into the runtime
registry via [`library-lab/library.yaml`](../../../library-lab/library.yaml)'s
`types:`/`plugins:` block — see [pipeline-steps.md](../../../lab/docs/pipeline-steps.md)
for the full catalog and how to query it live.

| Category | Examples |
|----------|----------|
| `extract/` | `extract_trace_stats`, `extract_mealy_stats`, `extract_trajectories` |
| `eval/` | `eval_mce`, `collect_metrics`, `compute_ci` |
| `viz/` | `plot_trajectory`, `ci_plot`, `plot_multilevel_trajectory` |
| `data/` | `to_dataframe`, `serialize`, `processor` |
| `services/` | `service_start`, `export_otel` |

Shared helpers: `pipeline/lib/` (`data_source`, `plot_lib`, `plot_specs/`).

Internal-only steps (`embed_states`, `list_clickhouse_sessions`) ship in
`mas-lab-internal/lab-components/bench-steps` and register via entry points when installed.

---

## Installation

```bash
uv pip install -e "mas-lab[all]"    # with all extras
uv pip install -e mas-lab/components/bench  # standalone
```

---

## Quick start

```bash
# 1. Write an experiment YAML  (see Experiment YAML format below)
# 2. Dry-run to validate config
mas-lab benchmark run my-experiment.yaml --dry-run

# 3. Execute (resumes if a prior run exists)
mas-lab benchmark run my-experiment.yaml --progress

# 4. Watch progress in another terminal
mas-lab benchmark follow my-experiment.yaml

# 5. Inspect results
mas-lab benchmark show last
```

---

## Experiment YAML format

```yaml
name: my-sre-ablation
n_runs: 5
output_dir: $XDG_DATA_HOME/mas/labs/results/my-ablation

mas_config: path/to/mas.yaml
flavour: local

scenarios:
  - path: datasets/scenarios.json     # multi-scenario dataset
    limit: 20                         # optional subset
  - id: single-scenario
    prompt: "CPU spike on prod-api-1"

overlays:                             # one experiment column per overlay
  - name: baseline
  - name: full_mitigation
    path: overlays/full.yaml
  - name: ablate_C7
    path: overlays/ablate-C7.yaml

pipeline: pipelines/post-process.yaml  # optional post-processing pipeline
```

---

## Commands

### `benchmark run`

Executes an experiment. Idempotent by default — a run with `n_runs: 5` resumes
from wherever it stopped. Results land in timestamped sub-directories under
`output_dir`.

```bash
mas-lab benchmark run experiment.yaml
mas-lab benchmark run experiment.yaml --force          # always start fresh
mas-lab benchmark run experiment.yaml --dry-run        # validate + plan only
mas-lab benchmark run experiment.yaml --single-run     # 1 scenario, handy for CI
mas-lab benchmark run experiment.yaml --limit-scenarios 10
mas-lab benchmark run experiment.yaml --sample-scenarios 20 --seed 42
mas-lab benchmark run experiment.yaml --max-runs 3
mas-lab benchmark run experiment.yaml --strategy depth # depth-first (default: coverage)
mas-lab benchmark run experiment.yaml -o /tmp/results
```

| Flag | Default | Description |
|------|---------|-------------|
| `--force` | off | Always create a new run |
| `--benchmark-id` | — | Resume a specific benchmark by ID |
| `--progress / --no-progress` | progress | Real-time progress bar |
| `--dry-run` | off | Validate config + show plan, no execution |
| `--max-runs` | from YAML | Override `n_runs` |
| `--limit-scenarios` | — | Limit to first N scenarios |
| `--sample-scenarios` | — | Randomly sample N scenarios |
| `--single-run` | off | Run exactly 1 scenario |
| `-o / --output-dir` | from YAML | Output directory |
| `--trace-cache` | `$XDG_CACHE_HOME/mas/traces` | Override trace-cache directory |
| `--force-lock` | off | Break existing lock |
| `--flavour` | `local` | Runtime flavour YAML name |
| `--strategy` | `coverage` | `coverage` (breadth-first) or `depth` (depth-first) |

### `benchmark list`

```bash
mas-lab benchmark list
mas-lab benchmark list --status completed
mas-lab benchmark list --limit 10 --format markdown
```

| Flag | Default | Description |
|------|---------|-------------|
| `--status` | — | Filter: `running` / `completed` / `failed` / `partial` |
| `--limit` | `20` | Max rows to show |
| `--format` | `simple` | `simple` / `markdown` / `csv` / `json` / `jsonl` |

### `benchmark show`

```bash
mas-lab benchmark show <id>
mas-lab benchmark show last
mas-lab benchmark show last plots
mas-lab benchmark show last events-trace
mas-lab benchmark show last otel-traces
mas-lab benchmark show last --format json
```

### `benchmark follow`

Polls `run_info.json` files and streams a running tally until all runs finish.
Use in a second terminal while `benchmark run` is executing.

```bash
mas-lab benchmark follow experiment.yaml
mas-lab benchmark follow experiment.yaml --interval 10
mas-lab benchmark follow experiment.yaml --once        # single snapshot
```

### `benchmark analyze`

Regenerates plots and statistics from existing run output (no re-execution).

```bash
mas-lab benchmark analyze <id>
mas-lab benchmark analyze <id> --experiment-yaml path/to/experiment.yaml
```

### `benchmark update`

Edit metadata of an existing run.

```bash
mas-lab benchmark update <id> --name "Final ablation v2"
mas-lab benchmark update <id> --add-tag ablation --add-tag final
mas-lab benchmark update <id> --remove-tag wip
```

### `benchmark step`

Inspect and restart individual pipeline steps within a run.

```bash
mas-lab benchmark step list <id>
mas-lab benchmark step show <id> <step_id>
mas-lab benchmark step restart <id> <step_id>
```

### `benchmark pipeline`

Executes a standalone post-processing pipeline YAML (normalize, graph export,
embed, evaluate, plot, …) against existing benchmark output.

```bash
mas-lab benchmark pipeline validate pipeline.yaml   # schema check
mas-lab benchmark pipeline show pipeline.yaml       # show step graph
mas-lab benchmark pipeline plan pipeline.yaml       # execution plan
mas-lab benchmark pipeline run pipeline.yaml
```

---

## Post-processing pipeline

Pipelines are YAML files that declare steps and their dependencies. Steps run
in topological order; independent steps run in parallel.

```yaml
name: post-process
steps:
  - name: extract
    type: extract_trajectories

  - name: stats
    type: extract_trace_stats
    depends_on: [extract]

  - name: eval
    type: eval_mce
    depends_on: [extract]
    config:
      events_path: "{{output_dir}}/runs/**/traces/events.jsonl"

  - name: plot
    type: plot
    depends_on: [eval]
    config:
      spec: shapley_bars
```

### Built-in step types

Registered step types are listed by `mas-lab benchmark pipeline validate` and in
[lab/docs/pipeline-steps.md](../../docs/pipeline-steps.md). Common OSS steps:

| Step type | Description |
|-----------|-------------|
| `experiment` | Run a MAS scenario via `mas-ctl` |
| `dataset` | Load / filter a scenario dataset |
| `extract_trajectories` | Build `trajectories.jsonl` from `events.jsonl` traces |
| `extract_trace_stats` | Aggregate per-run trace statistics |
| `eval_mce` | MCE LLM-as-judge scoring on `events.jsonl` |
| `annotate_metrics` | Attach metric scores to run metadata |
| `embed_trajectories` | Embed trajectory strings for manifold analysis |
| `plot` | Declarative figure from `plot_library/` spec (`shapley_bars`, `ablation_heatmap`, `trajectory_gantt`) |
| `plot_multilevel_trajectory` | Multilevel swimlane HTML/SVG from `events.jsonl` |
| `plot_trajectory` | Per-run trajectory SVG |
| `processor` | Run a registered trajectory processor by name |

---

## `eval` — MCE metrics on traces

```bash
mas-lab eval path/to/traces/events.jsonl --metric Groundedness --json
```

For batch scoring in benchmarks, use the `eval_mce` pipeline step on `events.jsonl`.

---

## `plot` — trace visualisations

Generate visualisations directly from a trace file:

```bash
mas-lab plot trajectory events.jsonl -o trajectory.png
mas-lab plot multilevel-trajectory events.jsonl -o multilevel.png
mas-lab plot communication-flow events.jsonl -o flow.png
mas-lab plot list output/benchmark/runs/
```

---

## Python API

```python
from mas.lab.benchmark.dataset import Dataset
from mas.lab.benchmark.experiment import ExperimentRunner, ExperimentConfig
from mas.lab.benchmark.metadata import BenchmarkMetadata

# Load dataset
dataset = Dataset.from_json("scenarios.json")
subset  = dataset.filter(category="timeout").sample(10, seed=42)

# Run experiment programmatically
config = ExperimentConfig(
    name="my-ablation",
    n_runs=5,
    output_dir="/tmp/my-ablation",
    mas_config="mas.yaml",
    overlays=["overlays/baseline.yaml", "overlays/full.yaml"],
)
runner = ExperimentRunner(config)
runner.run(dataset=subset, strategy="coverage")

# Query results
meta = BenchmarkMetadata.load("/tmp/my-ablation")
print(meta.status, meta.completed_runs, meta.total_runs)
```

---

## Package layout

```
components/bench/src/mas/lab/benchmark/
├── dataset.py              Dataset loading, filtering, sampling
├── experiment.py           ExperimentRunner + ExperimentConfig
├── metadata.py             BenchmarkMetadata (run_info.json)
├── lock.py                 Advisory file lock (concurrent-run safety)
├── deduplication.py        Trace-cache dedup (skip already-seen prompts)
├── analysis.py             Statistical analysis helpers
├── otel_collector.py       OTel span collection bridge
├── migrate.py              Run directory migration utilities
└── pipeline/
    ├── pipeline.py         Pipeline loader + validator
    ├── executor.py         Topological executor (parallel)
    ├── registry.py         Step-type registry
    ├── cache.py            Step output cache
    └── steps/
        ├── experiment.py
        ├── extract_trajectories.py
        ├── eval_mce.py
        ├── plot_multilevel_trajectory.py
        └── …
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [../../docs/benchmark.md](../../docs/benchmark.md) | Benchmark guide: quickstart, concepts, lifecycle |
| [../../docs/pipeline.md](../../docs/pipeline.md) | Pipeline architecture and YAML schema |
| [../../docs/pipeline-steps.md](../../docs/pipeline-steps.md) | Step type reference |
| [../../docs/pipeline-processors.md](../../docs/pipeline-processors.md) | Processor registry and plot library |
| [../../../library-eval/README.md](../../../library-eval/README.md) | MCE metrics and `mas-lab eval` |
| [../../docs/designing-experiments.md](../../docs/designing-experiments.md) | Designing ablations and Shapley experiments |
| [../../docs/benchmark-state-architecture.md](../../docs/benchmark-state-architecture.md) | Run state machine and locking |
| [../../docs/multi-scenario-format.md](../../docs/multi-scenario-format.md) | Multi-scenario dataset format |
