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

Benchmark runs accept repeatable schema-backed CLI overrides. The `experiment:`
root is patched before validation, scenario expansion, and dataset loading:

```bash
mas-lab benchmark run experiment.yaml \
  --override 'experiment:experiment.run.n_runs=1' \
  --override 'experiment:experiment.dataset.limit=2'
```

Reusable selector and wildcard groups belong in an Overlay manifest under
`spec.overrides`; see the [Overlay manifest reference](overlay.md) for the
target, patch, precedence, and validation contract.

---

## Four layers (matches CLI `--depth exp|scenario|item|run`)

There is **no** `pipelines:` key. Hooks live on the same objects the CLI
already names:

| YAML | CLI | Scope | Typical post |
| ------ | ----- | ------- | -------------- |
| `post:` (experiment root) | `--depth exp` | Whole experiment | `gather_level`, CI, plots |
| `scenario:` | `--scenario` / `--depth scenario` | One overlay column | Gather item frames |
| `item:` | `--item` / `--depth item` | One dataset item (all runs) | Gather run frames |
| `run:` | `--depth run` | Single run index | `eval_mce`, `metrics_to_dataframe`, `extract_trace_stats` |

`application:` is the **MAS binding** (`app` / `manifest` / `configs_dir`), not a pipeline level.
Deprecated aliases still load with a warning: `applications:`, `application.post`, `test:`.

Each level supports `pre:` and `post:` as **lists of steps** (0..N).

---

## Core fields

```yaml
experiment:
  name: topology-ablation
  model: any                    # shorthand for models.main; omit ≡ any
  models:                       # optional slot map (main / summarizer / judge)
    main: any

  # ── Application ── MAS + experiment-level post (gather → CI → figure)
  application:
    app: trip-planner
    configs_dir: ./overlays
    # Preferred for shared apps — library identifier + versioned app id:
    # app: example-library:my-app@v2
    # manifest: example-library:apps/my-app/v2/mas.yaml
  artifacts: {df: dataframe}
  post:
    - {name: gather-experiment, type: gather_level, in: df, out: df, depends_on: [gather-scenario]}

  # ── Scenario ── overlay columns + gather
  scenarios:
    - id: linear
      overlays: {logic: [linear], control: [], infra: []}
  scenario:
    artifacts: {df: dataframe}
    post:
      - {name: gather-scenario, type: gather_level, in: df, out: df, depends_on: [gather-item]}

  # ── Item ── dataset item + gather
  dataset:
    name: trip-planner-benchmark
    locator: samples
    # limit: 10   # optional: first N items; omit to run the full Dataset
  item:
    artifacts: {df: dataframe}
    post:
      - {name: gather-item, type: gather_level, in: df, out: df, depends_on: [extract-trace-stats]}

  # ── Run ── one MAS execution; n_runs lives here
  run:
    n_runs: 5
    artifacts:
      trace: trace
      df: dataframe
    post:
      - name: extract-trace-stats
        type: extract_trace_stats
        in: trace
        out: df

  # ── Execution ── batch orchestration only (last)
  execution:
    parallel_scenarios: 4
    timeout: 300
    strategy: coverage
```

---

## Model slots (`models` / `model`)

Named slots, not `$variables`. Keys match Agent/MAS `spec.models[].id`, plus
`judge`. Agents that say `model: any` inherit the experiment (then MAS, then
local `config.yaml`). Scalar `experiment.model` is **shorthand for
`models.main`**; `models.main` wins when both are set.

```yaml
experiment:
  models:
    main: gpt-4o                # turn default (fills Agent/MAS model: any)
    summarizer: gpt-4o-mini     # summary default when params.model omitted
    judge: gpt-4o-mini          # MCE default; evaluation.model still wins
```

`evaluation.model` and `eval_mce.config.model` remain judge-only overrides.
`summarizer.params.model` remains a per-agent summary override. Overlay the
graph (tools, pattern); pin models here.

See [summarization.md](summarization.md) for the full chain.

---

## Evaluation model (`evaluation.model`)

`eval_mce` defaults to `experiment.models.judge`, then `models.main` /
`experiment.model`, then the application MAS/Agent `spec.models[]`. `any`
(or omitted) means the spec does not pin a provider id — local `config.yaml`
`defaults.model` fills it. Override the judge with `experiment.evaluation.model`;
a per-step `eval_mce.config.model` still wins.

```yaml
experiment:
  models:
    main: gpt-4o
    judge: gpt-4o-mini          # or evaluation.model: gpt-4o-mini
  applications:
    - manifest: ./mas.yaml
  evaluation:
    method: llm_judge
  application:
    post:
      - {type: eval_mce, depends_on: [extract_trajectories]}
```

See [summarization.md](summarization.md#mce-judge-model) for resolution order
and logs. Feature example (not a sample app):
[library-eval/examples/mce/judge-override/](../../library-eval/examples/mce/judge-override/).

---

## Applications

`experiment.applications` is the MAS pointer (`app:` catalog id or `manifest:` path).

```yaml
applications:
  - app: example-library:my-app@v1
    configs_dir: ./overlays
```

`experiment.mas` (and `lab.mas` in `lab-config.yaml`) is a **deprecated** alias of
`applications[0]`. Loaders still accept it and emit a warning. Rewrite:

```yaml
# before
mas:
  manifest: ../../apps/my-app/mas.yaml
  configs_dir: overlays

# after
applications:
  - app: example-library:my-app@v1
    configs_dir: overlays
```

Relative `manifest:` paths still work; prefer `app: library:id@version`.

---

## Pipeline reference forms

| Form | Example |
| ------ | --------- |
| Library id | `{ id: analysis }` or shorthand string in lists |
| File ref | `./pipelines/post-run.yaml` or `{ ref: ... }` |
| Inline steps | `{ steps: [{ name: s1, type: plot_trajectory, ... }] }` |

---

## Checkpoint axis

`experiment.checkpoints` is an optional starting-state axis crossed with
`scenarios`, dataset items, and `run.n_runs`. Omit it to preserve the existing
matrix. The `none` entry is a fresh start and can sit beside saved states for a
direct what-if comparison:

```yaml
experiment:
  checkpoints:
    - id: none
    - id: after-triage
      path: ./checkpoints/after-triage.checkpoint.json
```

Each entry needs a unique alphanumeric, dash, or underscore `id`. Every entry
except `none` needs a checkpoint `path`, resolved relative to the experiment
YAML. A non-trivial axis overrides an item's own `inputs.checkpoint.load` and
emits a warning when both are set. With no axis, item-level loading is used
directly. Checkpoint IDs and source paths are written to `results.csv` and
`session_mappings.jsonl` alongside each run's session ID.

See the [checkpoint-axis example](../schemas/examples/checkpoint-axis.yaml)
and [Tutorial 6](../tutorials/06-sessions-and-recovery/README.md).

---

## Artifacts

`artifacts:` declares typed outputs (`trace`, `metrics`, `dataframe`, `plot`, …) at each
level. Short form names just the type (`metrics: metrics`); long form overrides the path
template and turns on schema validation:

```yaml
run:
  artifacts:
    trace: { type: trace, path: "{run_dir}/traces/events.jsonl" }
    metrics: metrics
    df: { type: dataframe, path: "{level_dir}/data.csv" }
  post:
    - name: eval-quality
      type: eval_mce
      in: trace     # reads this level's `trace` artifact
      out: metrics  # writes this level's `metrics` artifact

item:
  artifacts:
    df: { type: dataframe, path: "{level_dir}/data.csv" }
  post:
    - name: gather-test
      type: gather_level
      in: df        # fans in every child `run`'s `df` instance
      out: df        # writes this level's own `df`
```

A step's `in:` names an artifact declared at the level **below** its own scope — the
executor resolves every child instance's file path and passes them as
`config["artifact_paths"]`. `out:` just documents which of this level's own declared
artifacts the step produces; nothing enforces it beyond the step's own config
(`output:`/`output_dir:`).

---

## `output_schema:`

Optional fail-fast check on the final output directory — declares files that must
exist and, per file, columns that must be present:

```yaml
experiment:
  output_schema:
    required_files:
      - "results/ci_summary.csv"
    required_columns:
      results/ci_summary.csv: [scenario, metric, mean, ci_low, ci_high]
```

Declaring it doesn't run the check by itself — add a `validate_outputs` step
(typically last in `application: post:`) with `config: {schema: <the output_schema
dict above>}`; see [pipeline-steps.md](../../lab/docs/pipeline-steps.md).

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
| LLM endpoints, cache middleware | Workspace `infra_refs`, `--infra-ref`, optional `mas-lab benchmark --infra <name>` (local `infra/<name>.yaml`) |
| Per-turn engine tuning (queue depth, LLM response cache read/write, stream, parallel tools) | `kind: RuntimeEngine` via `runtime_refs` / `--runtime-ref` — see [runtime-engine.md](runtime-engine.md) |
| How many MAS runs run in parallel, timeouts, ordering, failed-run reattempts | `experiment.execution.parallel_scenarios`, `timeout`, `strategy`, `max_attempts` (default 3) |
| Whole-run trace skip/replay (content-addressed lab cache) | `experiment.execution.emulation.runtime.cache` (`content-addressed` \| `disabled` \| `forced`) |
| Live vs replay for LLM, tools, memory during a benchmark | `experiment.execution.emulation.infra.*` |

Example (smoke run — disable trace cache, keep infra live). Put `execution:` last:

```yaml
experiment:
  name: my-bench
  application:
    app: trip-planner
    configs_dir: ./overlays
  run:
    n_runs: 1
  execution:
    emulation:
      runtime:
        cache: disabled
```

Implementation types: `mas.lab.lab.config.execution` (`MASExecutionSpec`, `EmulationSpec`).

---

## Dataset

`experiment.dataset.name` is a catalog id (`locator: samples`) or a lab-local
`datasets/<name>.yaml`. Nested experiments (`01-foo/experiment.yaml`) resolve
the lab root `datasets/` automatically.

`dataset.limit` takes the first N items. Use that for smoke and CI. Do not
check in a reduced copy of the same pack (`*-100.yaml`).

```yaml
dataset:
  name: trip-planner-benchmark
  locator: samples
  limit: 5
```

---

## See also

- [lab.md](lab.md)
- [pipeline.md](pipeline.md)
- [summarization.md](summarization.md) — judge model + conversation summarization
- [Tutorial 03](../tutorials/03-experiments-and-analysis/README.md)
- [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md)
