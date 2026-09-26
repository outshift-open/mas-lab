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

## Evaluation model (`evaluation.model`)

`eval_mce` defaults to the **same model the agent used**
(`metadata.model_name`, then workspace infra). Override once on the lab spec;
a per-step `eval_mce.config.model` still wins.

```yaml
experiment:
  metadata:
    model_name: gpt-4o
  evaluation:
    method: llm_judge
    model: gpt-4o-mini          # judge; omit to use gpt-4o
  application:
    post:
      - {type: eval_mce, depends_on: [extract_trajectories]}
```

See [summarization.md](summarization.md#mce-judge-model) for resolution order
and logs. Feature example (not a sample app):
[library-eval/examples/mce/judge-override/](../../library-eval/examples/mce/judge-override/).

---

## Pipeline reference forms

| Form | Example |
|------|---------|
| Library id | `{ id: analysis }` or shorthand string in lists |
| File ref | `./pipelines/post-run.yaml` or `{ ref: ... }` |
| Inline steps | `{ steps: [{ name: s1, type: plot_trajectory, ... }] }` |

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

test:
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
- [summarization.md](summarization.md) — judge model + conversation summarization
- [Tutorial 03](../tutorials/03-experiments-and-analysis/README.md)
- [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md)
