<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Pipeline guide

A **pipeline** is a list of **pipeline steps** that run after **benchmark**
execution and write shared artifacts under `results/`.

Terms: [glossary.md](../../docs/glossary.md).

## Embedded vs standalone

**Embedded pipeline** — level hooks inside `experiment.yaml`; runs automatically
when you `mas-lab benchmark run`. There is no `pipelines:` attribute.
A neighbouring `pipeline.yaml` is not loaded unless the manifest or CLI
`--pipeline` names that file.

```yaml
experiment:
  application:
    app: trip-planner
    configs_dir: ./overlays
  run:
    artifacts:
      trace: trace
      df: dataframe
    post:
      - name: extract-trace-stats
        type: extract_trace_stats
        in: trace
        out: df
  item:
    artifacts: {df: dataframe}
    post:
      - {name: gather-item, type: gather_level, in: df, out: df, depends_on: [extract-trace-stats]}
  scenario:
    artifacts: {df: dataframe}
    post:
      - {name: gather-scenario, type: gather_level, in: df, out: df, depends_on: [gather-item]}
  post:
    - name: gather-experiment
      type: gather_level
      in: df
      out: df
      depends_on: [gather-scenario]
```

CLI `--depth exp|scenario|item|run` selects which of these hooks to inspect.
Deprecated: `application.post` (use experiment-level `post:`) and `test:` (use `item:`).

**Per-run hook** — `run.post`; runs once after **each individual run**
`(scenario × item × run_idx)`:

```yaml
experiment:
  run:
    n_runs: 3
    post:
      - ref: pipelines/post-run.yaml    # file ref; steps inside use per_run: true
```

Steps in a `run.post` pipeline receive the run's execution context via
`ctx.scope_context` (scenario, item, run index).  Use `per_run: true` on each
step that needs per-run access:

```yaml
# pipelines/post-run.yaml
spec:
  steps:
    - name: eval-booking
      type: lib/steps/my_eval.py:MyEvalStep   # path relative to experiment dir
      per_run: true
      config:
        reference_path: datasets/reference/fares.yaml
```

**Hook levels** (outermost → innermost):

| YAML key | Fires | Typical use |
|----------|-------|-------------|
| experiment `post:` | Once, after all scenarios complete | CI aggregation, figures |
| `scenario.post` | Once per scenario, after all items | Per-scenario summaries |
| `item.post` | Once per (scenario × item), after all runs | Cross-run comparison |
| `run.post` | Once per run | Per-run evaluation, OTel export |

**Standalone pipeline** — separate YAML; use when **runs** already exist:

```bash
mas-lab benchmark pipeline run labs/.../pipeline-figure.yaml -o $XDG_DATA_HOME/mas/labs/my-exp
```

Schema: [manifests/pipeline.md](../../docs/manifests/pipeline.md).

## Per-run artifact access

Inside a `per_run: true` step, use the canonical helpers — **never** read
`.run_ref` directly:

```python
from mas.lab.benchmark.pipeline.run_artifacts import resolve_run_events, run_dir_from_ctx

async def execute(self, ctx):
    run_dir    = run_dir_from_ctx(ctx, self.config)   # benchmark r1/ dir
    events_path = resolve_run_events(ctx, self.config) # handles .run_ref + inline
```

`run_dir_from_ctx` derives the run directory from `ctx.scope_context` when
present (the `per_run: true` code path), with a `config["run_dir"]` fallback
for backward compatibility.  `resolve_run_events` handles all storage modes:
inline `traces/events.jsonl`, symlinked `traces/` directory, and `.run_ref`
content-addressed cache indirection.

## Step catalog

[pipeline-steps.md](pipeline-steps.md).

## Step caching

Each step writes a fingerprint under `<output_dir>/.cache/<step>.fingerprint`.
A later `mas-lab benchmark run` (or `benchmark pipeline run`) skips a step
when its type, config, and upstream fingerprints are unchanged. Downstream
steps rerun when an upstream fingerprint changes.

```bash
mas-lab benchmark step restart <benchmark-id> <step-id>   # one step
mas-lab benchmark pipeline run pipeline.yaml -o DIR --force STEP
```

See [benchmark CLI](../src/mas/lab/cli/commands/benchmark/) and
[benchmark-state-architecture.md](benchmark-state-architecture.md) for
how this relates to the run-level trace cache.

## Custom steps

[custom-pipeline-steps.md](custom-pipeline-steps.md) — authoring guide,
`per_run: true` pattern, artifact resolution APIs, fixture evaluation,
`register_steps.py`, and the `pkg://` vs scheme syntax for tool refs.
