<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Lab quickstart

A **lab** is a folder ending in `.lab` with an **experiment** manifest
(`experiment.yaml`): which **scenarios** and **dataset** items to run, and which
**pipeline** steps turn **runs** into tables and figures.

Full term list: [glossary.md](../../docs/glossary.md). Default paths:
[`docs/user-config.md`](../../docs/user-config.md).

## What one command does

```bash
export PATH="$PWD/.venv/bin:$PATH"
mas-lab benchmark run labs/lifecycle-control.lab/experiment.yaml --progress
```

`mas-lab benchmark run` has two phases:

1. **Execution** — For each **scenario** (setup), each **dataset** item, and each
   repeat (`n_runs`), the runtime executes the **agent** or **MAS** and writes
   **`events.jsonl`** under `traces/`. Identical work is skipped via the **trace
   cache**.

2. **Embedded pipeline** — The `pipeline:` block in the same `experiment.yaml`
   runs automatically. Each **pipeline step** reads logs and writes CSV/PNG files
   into `results/`.

Paper figures come only from this command (phase 1 + embedded pipeline). Do not
use standalone plotting scripts.

## What you need installed

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- An OpenAI-compatible API (`OPENAI_API_KEY`, optional `OPENAI_API_BASE`)
- Repo cloned; from root: `uv sync --all-packages`

Install walkthrough: [Tutorial 0](../../docs/tutorials/00-environment-setup/README.md).

## Where output goes

With `$XDG_CONFIG_HOME/mas/config.yaml`, results use `experiment.name`:

```text
$XDG_DATA_HOME/mas/labs/<experiment-name>/results/
  trace_stats.csv
  mealy_stats.csv
  fig-*.png
  metadata.json
```

Paths: [user-config](../../docs/user-config.md).

## Inspect results

```bash
mas-lab benchmark show last
mas-lab benchmark show last plots
mas-lab benchmark list --limit 5
```

## Smoke runs (fewer scenarios / runs)

```bash
mas-lab benchmark run labs/design-space.lab/01-design-patterns/experiment.yaml --dry-run

mas-lab benchmark run labs/design-space.lab/01-design-patterns/experiment.yaml \
  --limit-scenarios 2 --max-runs 1 --progress
```

## Re-run without new LLM calls

Re-run the same command. Cached **runs** are skipped; **pipeline steps** refresh
when inputs or step code change.

```bash
mas-lab benchmark run labs/lifecycle-control.lab/experiment.yaml --progress
```

Pipeline only (logs already on disk):

```bash
mas-lab benchmark pipeline run labs/design-space.lab/01-design-patterns/pipeline-figure.yaml \
  -o $XDG_DATA_HOME/mas/labs/lab1-exp1.1-design-patterns-qa
```

## Paper experiments

| Paper § | Command |
|---------|---------|
| §5.1a design patterns | `mas-lab benchmark run labs/design-space.lab/01-design-patterns/experiment.yaml` |
| §5.1b topologies | `mas-lab benchmark run labs/design-space.lab/02-topologies/experiment.yaml` |
| §5.2 lifecycle | `mas-lab benchmark run labs/lifecycle-control.lab/experiment.yaml` |
| §5.3 extensions | `mas-lab benchmark run labs/extensions.lab/experiment.yaml` |
| All | `task reproduce` |

Details: [paper/index.md](../../docs/paper/index.md).

## Observability in benchmarks

Benchmarks enable **`events.jsonl`** via **flavour** and **overlays** inside the
experiment manifest — not via `mas-ctl --events` on the benchmark CLI.
See [cli/observability.md](../../docs/cli/observability.md).

## Next

- [labs-going-further.md](labs-going-further.md) — custom pipeline steps and scenarios
- [Tutorial 3](../../docs/tutorials/03-experiments-and-analysis/)
- [benchmark.md](benchmark.md) — benchmark CLI reference
