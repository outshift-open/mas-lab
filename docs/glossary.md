<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Glossary (manifests & experiments)

Terms you will see in YAML files and CLI output every day. Each user guide
also explains them in context; this page is the single reference list.

| Term | Meaning |
|------|---------|
| **Manifest** | A YAML file that declares an agent (`agent.yaml`), a multi-agent team (`mas.yaml`), an experiment (`experiment.yaml`), an overlay, a flavour, etc. |
| **MAS** | Multi-agent system — several agents with a workflow (who talks to whom). Configured in a `mas.yaml` manifest. |
| **Agent** | Single LLM actor with tools, skills, and plugins. Configured in an `agent.yaml` manifest. |
| **Overlay** | A small YAML patch (`kind: Overlay`) merged on top of a manifest. CLI: `-o path/to/overlay.yaml`. Used to vary one knob (tools, memory, governance) without copying the whole file. |
| **Flavour** | Deployment preset: model endpoint, instrumentation, transport. Referenced from experiments or `config.yaml` (e.g. `standard:openai`). |
| **Lab (definition)** | A folder `*.lab/` (under `labs/`) with `experiment.yaml`, datasets, overlays, and optional custom pipeline steps. Data/config, not code. |
| **Package** | A published wheel (`mas-runtime`, `mas-ctl`, `mas-lab`, …). See [packages reference](packages-reference.md). |
| **Component** | One of the four lab sub-wheels under `lab/components/` (`mas-lab-core`, `mas-lab-bench`, `mas-lab-controller`, `mas-lab-content`). The interactive tutorial runner (`mas-lab-tutorial`) is internal-only — see `mas-lab-internal`. Distinct from the internal `mas.lab.*` runtime modules — see [ADR 0001](references/adr-0001-lab-terminology.md). |
| **Experiment** | The `experiment:` block (usually in `experiment.yaml`): what to run, how many times, and which pipeline builds results. |
| **Scenario** | One column in an experiment matrix — a named setup (`id`) and which overlays apply. Declared under `scenarios:`. |
| **Dataset** | Input items (prompts, expected fields) the experiment iterates over. Referenced as `dataset:` in `experiment.yaml`. |
| **Run** | One execution of the agent/MAS for a given (scenario, dataset item, repeat index). Produces `traces/events.jsonl`. |
| **`n_runs`** | How many times to repeat each (scenario, item) for variance. |
| **Benchmark** | `mas-lab benchmark run` — executes all runs, then runs the pipeline. |
| **Pipeline** | Ordered **pipeline steps** that read run artifacts and write CSV/PNG under `results/`. |
| **Embedded pipeline** | The `pipeline:` list inside `experiment.yaml` — runs automatically after the benchmark execution phase. |
| **Pipeline step** | One unit in the pipeline (e.g. `extract_trace_stats`, `plotnine`). Declared with `name`, `type`, `config`. |
| **`events.jsonl`** | Machine-readable run log: one JSON object per line (model calls, tool calls, governance, routing). |
| **Exchange log** | Human-readable transcript on stderr during `mas-ctl chat` (`--trace`). Not used for experiment scoring. |
| **Trace cache** | Store of completed run logs; identical inputs reuse the cache instead of calling the model again. |
| **Observability** | Settings that enable `events.jsonl` (manifest `spec.observability`, overlay, or `--events`). |

Runtime internals: see the `runtime/docs/` tree in the repository.

Hub: [references/index.md](references/index.md) · Run logs:
[cli/observability.md](cli/observability.md).
