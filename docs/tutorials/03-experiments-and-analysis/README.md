<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 3 — Experiments, Analysis & Evaluation

> **Packages:** `mas-lab`, `mas-runtime`
> **Time:** ~60 min hands-on
> **Prerequisite:** [Tutorial 0](../00-environment-setup/) (data paths),
> [Tutorial 1](../01-building-an-agent/), and [Tutorial 2](../02-creating-a-mas/).
> Run `mas-lab config` to see where this machine stores labs output and trace cache.

---

## Overview

In Tutorials 1 and 2 you built an agent and composed a MAS.
Now you'll learn how to **run experiments and analyze the output**: define
benchmarks with `experiment.yaml`, inspect raw **`events.jsonl`** traces,
evaluate answer quality with MCE, and generate plots — first
manually, then via reusable pipelines, and finally in a full experiment
comparing three MAS topologies on the trip planner.

1. **Part A** — Manual trace analysis on a QA agent (CLI commands one by one)
2. **Part B** — Turning those manual steps into a declarative pipeline
3. **Part C** — Trip planner experiment: single-agent vs. linear vs. moderator, evaluated with MCEv1 `AnswerRelevancyMetric` and compared in a grouped ggplot2 plot

---

## Part A — Manual Trace Analysis

Part A uses the same Q&A agent from Tutorial 1, running three design
pattern variants (ReAct, CoT, Reflection) so you can inspect the
differences in raw traces. **You must run this tutorial's benchmark first**
— the traces don't come from Tutorial 1's output.

```bash
# From repository root (or cd into the tutorial directory)
mas-lab benchmark run docs/tutorials/03-experiments-and-analysis/experiment.yaml --progress
```

Offline analysis (no LLM) uses the bundled fixture trace — see `demo/scenario.yaml` and:

```bash
pytest tests/tutorials/test_scenario_commands.py -v -k tuto-03
```

### Where traces are stored

The runner **auto-derives** the output directory from the experiment's
`name:` field.  No `output_dir:` is needed in `experiment.yaml`.

**Check your machine first** (paths depend on `~/.mas/config.yaml`):

```bash
mas-lab config
```

| Config | Labs root | Trace cache |
|--------|-----------|---------------|
| `~/.mas/config.yaml` with `labs_dir` / `cache_dir` | `~/.mas/labs/` | `~/.mas/cache/traces/` |

Create `~/.mas/config.yaml` if it does not exist — see [Tutorial 0](tutorials/00-environment-setup/README.md) or run `mas-lab config` to inspect paths.

Tutorial 3's experiment (`name: "t3-observability-patterns"`) writes to:

```
<labs_root>/t3-observability-patterns/
```

For example, with default user config: `~/.mas/labs/t3-observability-patterns/`.

> **Override:** `labs_dir` / `cache_dir` in `~/.mas/config.yaml`, or env vars
> `$MAS_LABS_ROOT`, `$MAS_TRACE_CACHE`, `$MAS_DATA_CACHE`.  Inside a `.lab`
> workspace the path becomes `<labs_root>/<lab_name>/<experiment_name>/`.

Resolve paths once per shell session (values depend on your `~/.mas/config.yaml`):

```bash
export LABS_ROOT="$(python -c 'from mas.lab.paths import labs_root; print(labs_root())')"
export TRACE="$LABS_ROOT/t3-observability-patterns/react/item1/r1/traces/events.jsonl"
```

The runner creates a directory tree mirroring the experiment hierarchy
(`scenario / item / run`):

```
$LABS_ROOT/t3-observability-patterns/                  ← auto-derived from name
├── metadata.yaml                                      ← experiment metadata
├── react/                                             ← scenario
│   ├── item1/                                         ← dataset item
│   │   └── r1/                                        ← run number
│   │       ├── traces/                                ← trace artifacts (*)
│   │       │   └── events.jsonl                       ← raw event stream
│   │       ├── run_info.json                          ← timing, status, config
│   │       └── .run_ref                               ← cache hash pointer
│   └── item2/
│       └── r1/
│           └── ...
├── cot/
│   └── ...
└── reflection/
    └── ...
```

**(\*) `traces/` is a symlink.** The actual `events.jsonl` lives in a
content-addressed **trace cache** (see `mas-lab config` for the path, typically
`~/.mas/cache/traces/<hash>/traces/`).
The runner hashes deterministic inputs (resolved config, prompt, model, run
index) and stores the trace once. The symlink in the output dir points to the
cache entry:

```
traces/ → <trace_cache>/<hash>/traces/
```

This deduplication means: if you re-run the same experiment with the same
inputs, the cache is hit and no new trace is produced. To force a fresh run,
delete the `.run_ref` file (breaks the link) and re-execute.

### A.1 — The raw event stream

Every agent run produces an `events.jsonl` — one JSON object per line, one
event per runtime boundary crossing (LLM call, tool call, session lifecycle):

```bash
head -5 "$TRACE"
# offline: head -5 docs/tutorials/03-experiments-and-analysis/fixtures/events.jsonl
```

```json
{"event": "session_start", "agent": "qa-agent", "timestamp": "2026-04-19T10:23:01Z", "trace_id": "a1b2c3"}
{"event": "llm_call_start", "agent": "qa-agent", "model": "gpt-4o-mini", "dp_state": {"phase": "think", "iteration": 1}}
{"event": "llm_call_end", "agent": "qa-agent", "tokens": {"prompt": 312, "completion": 87}, "duration_ms": 1240}
{"event": "tool_call_start", "agent": "qa-agent", "tool": "calculator", "args": {"expression": "17 * 23"}}
{"event": "tool_call_end", "agent": "qa-agent", "tool": "calculator", "result": {"value": 391}, "duration_ms": 2}
```

Key fields:

| Field | Description |
|-------|-------------|
| `event` | Event type — `session_start`, `llm_call_start/end`, `tool_call_start/end`, `session_end` |
| `agent` | Which agent emitted this event |
| `dp_state` | Design pattern state — phase (`think`/`act`/`observe`), iteration number |
| `trace_id` | Correlation ID linking all events in the same session |

### A.2 — Telemetry summary

```bash
mas-lab telemetry show "$TRACE"
# offline: mas-lab telemetry show docs/tutorials/03-experiments-and-analysis/fixtures/events.jsonl
```

Output: event count, agents involved, time range, token usage, event
breakdown by type. This is the quickest way to sanity-check a run.

Inspect tool calls directly:

```bash
grep '"tool_call_start"' "$TRACE" \
  | python3 -c "
import sys, json
for line in sys.stdin:
    e = json.loads(line)
    args = e.get('arguments') or e.get('args') or {}
    print(f\"  {e.get('tool_name') or e.get('tool')}({args})\")
"
```

On the bundled ReAct trace you should see a multiply step followed by systematic
trial division (nine tool calls for primality checking).

### A.3 — Knowledge graph (proprietary extension)

Graph normalization (`mas-lab graph normalize`), structural validation, and
OTel span export (`mas-lab graph events-to-otel`) are **not** part of this
open-source repository.

This OSS tutorial continues with **telemetry**, **plots**, and **benchmarks**
on `events.jsonl` directly.

### A.4 — Evaluation (MCEv1)

Evaluation measures **answer quality**. The `AnswerRelevancyMetric` uses an
LLM-as-judge to score how well the agent's response addresses the input:

```bash
mas-lab eval-output "$TRACE" \
  --metric AnswerRelevancyMetric \
  --model gpt-4o \
  --api-key-env OPENAI_API_KEY
```

Output: a JSON object with `score` (0–1), `reason` (explanation from the judge),
and metadata:

```json
{
  "metric": "AnswerRelevancyMetric",
  "score": 0.92,
  "reason": "The response correctly computes 17*23=391 and accurately verifies primality.",
  "model": "gpt-4o",
  "session_id": "a1b2c3"
}
```

### A.5 — Trajectory plots

#### Compact delegation diagram (SVG)

```bash
mas-lab plot trajectory "$TRACE" \
  --format svg -o output/trajectory-item1.svg
```

For a single agent this is a linear sequence; for a MAS (Tutorial 2) it
shows delegation arrows between agents.

#### Interactive swimlane (HTML)

```bash
mas-lab plot multilevel-trajectory "$TRACE" \
  --format html -o output/swimlane-item1.html
```

The HTML view has:

- Horizontal lanes per agent
- Tool calls as blocks within lanes
- `dp_state` annotations on each block (ReAct iteration, think/act/observe)
- Clickable events for full detail

---

## The experiment.yaml hierarchy

Before diving into pipelines and full experiments, let's understand the
**four-level hierarchy** that structures every benchmark:

```
EXPERIMENT ─── the top-level unit of work
├── APP (applications:) ── one or more MAS applications under test
│   └── SCENARIO ───────── a configuration variant (overlay stack)
│       └── TEST ───────── one dataset item (prompt, incident, trip…)
│           └── RUN ────── a repeated execution (n_runs times)
```

| Level | Defined by | Multiplicity |
|-------|-----------|--------------|
| **Experiment** | `experiment.yaml` | 1 |
| **App** | `applications:` list (manifest + overlays dir) | 1+ per experiment |
| **Scenario** | `scenarios:` list — each entry is an overlay stack | M scenarios |
| **Test** | one item in `dataset.yaml` (app-specific) | D items per dataset |
| **Run** | `run.n_runs` | N repetitions per test |

**Total executions = M × D × N**

The output directory mirrors this structure:

```
$LABS_ROOT/<experiment_name>/
└── <scenario_id>/
    └── <item_id>/
        └── r<N>/
            └── traces/events.jsonl
```

### What lives at each level

**Scenarios** define the **independent variable** — the configuration change
you're testing. Each scenario explicitly declares its **overlays** — configuration
patches applied on top of the base MAS manifest:

```yaml
scenarios:
  - id: baseline                # ← scenario id (used for output dirs)
    overlays: []                # ← no overlays (control)
    tags: [reference]
  - id: cot                     # ← scenario id
    overlays: [cot]             # ← overlays/cot.yaml via metadata.id
    tags: [cot]
  - id: biased-confirmation
    overlays: [biased-confirmation]  # ← MITM fault overlay
    tags: [mitm, bias]
```

**Tests** come from the dataset, which is **app-specific** — a Q&A agent
gets prompts, a trip planner gets trip requests, an SRE system gets
incident scenarios:

```yaml
dataset:
  path: "dataset.yaml"          # items: [{id: "item1", prompt: "..."}, ...]
```

**Runs** repeat each test to measure variance:

```yaml
execution:
  n_runs: 3                     # 3 repetitions per (scenario × item)
  strategy: coverage            # breadth-first: one round across all conditions
```

### Named resources and pipelines

Pipeline steps run after the benchmark and operate at a specific
**scope** in the hierarchy. For the OSS release profile, Tutorial 3 keeps
inline pipelines empty and uses a standalone, re-runnable analysis pipeline.

```yaml
application:
  post:
    - name: extract
      type: extract_trajectories
      scope: app              # ← runs once for the whole experiment
      config:
        runs_dir: runs
        csv_file: mas_benchmark_*.csv
```

| Scope | Runs | Template variables available |
|-------|------|-----------------------------|
| `run` | once per run | `{scenario_id}`, `{item_id}`, `{run_dir}`, `{events_jsonl}` |
| `item` | once per (scenario × item) | `{scenario_id}`, `{item_id}` |
| `scenario` | once per scenario | `{scenario_id}` |
| `app` | once total | `{output_dir}` |

### Tutorial artifacts vs. design-space lab

This tutorial is **self-contained** under `docs/tutorials/03-experiments-and-analysis/`.
For larger sweeps (100-item QA dataset, trip-planner topologies), see
`labs/design-space.lab/` in the repository root.

| Tutorial file | Experiment `name:` | Output directory |
|---------------|-------------------|------------------|
| `experiment.yaml` | `t3-observability-patterns` | `$LABS_ROOT/t3-observability-patterns/` |
| `experiment-topology.yaml` | `t3-topology-comparison` | `$LABS_ROOT/t3-topology-comparison/` |

The experiment `name:` field drives the auto-derived output directory under
`labs_dir` from `~/.mas/config.yaml`.

---

## Part B — From Manual Commands to Pipelines

Part A used manual CLI commands. A **pipeline** declares the same steps in
YAML, with explicit dependencies, so they run automatically after every
benchmark.

### B.1 — Pipeline structure

```yaml
# pipelines/analysis.yaml
api_version: "pipeline/v1"
kind: Pipeline

metadata:
  name: t3-observability-patterns
  description: "Release-safe analysis: extract trajectories"

spec:
  steps:
    - name: extract
      type: extract_trajectories
      config:
        runs_dir: runs
        csv_file: mas_benchmark_*.csv
```

### B.2 — One step per manual command

| Manual command (Part A) | Pipeline step type | Produces |
|------------------------|-------------------|----------|
| benchmark post-processing | `extract_trajectories` | `trajectories.jsonl` + per-run `trajectory.json` |

### B.3 — Dependencies

```
extract
```

The standalone pipeline is intentionally minimal for release validation and
clean-environment reproducibility.

### B.4 — Running the pipeline

```bash
T03=docs/tutorials/03-experiments-and-analysis

# Full pipeline (after a benchmark run)
mas-lab benchmark pipeline run "$T03/pipelines/analysis.yaml"

# Single step (re-run evaluation only)
mas-lab benchmark pipeline run "$T03/pipelines/analysis.yaml" --only evaluate

# Dry run
mas-lab benchmark pipeline run "$T03/pipelines/analysis.yaml" --dry-run
```

### B.5 — Inline vs. standalone pipelines

Pipelines can also be **inlined** in the experiment YAML (`application.post`
and other level hooks). Use inline for simple post-processing;
use standalone `.yaml` files when you want to re-run analysis without
re-executing the benchmark.

---

## Part C — Trip Planner Topology Comparison

Now for a real experiment. The trip planner MAS
(`ctl/examples/trip-planner/`) uses a moderator + 3 specialists. But is
that topology actually better? Let's compare three approaches:

| Topology | `routing.type` | Description | Config |
|----------|---------------|-------------|--------|
| **Single-agent** | `single` | One agent with all tools — no delegation | `topologies/single-agent.yaml` |
| **Sequential** | `sequential` | Automaton walks agents in order, accumulating context | `topologies/linear.yaml` |
| **Moderator** | `llm-routed` | Moderator LLM orchestrates 3 specialists dynamically | `topologies/moderator.yaml` |

### C.1 — The three topologies

#### Single-agent (`routing.type: single`)

One agent receives all tools and handles the entire trip planning request.
No delegation, no routing logic — the agent's ReAct loop does everything:

```yaml
# topologies/single-agent.yaml
apiVersion: mas/v1
kind: MAS
metadata:
  name: trip-planner-single

spec:
  agents:
    - id: generalist
      ref: agents/moderator/agent.yaml
      tools: [lookup_schedule, query_graph_database, get_fares, calc]
      skills: [trip-orchestration, transport-schedule-lookup,
               route-planning, fare-and-itinerary-assembly]

  routing:
    type: single
    entry: generalist
    nodes:
      - id: generalist
        role: specialist
```

#### Sequential (`routing.type: sequential`)

Three specialists in a fixed order. An **automaton** (not an LLM) drives
the pipeline: schedule → itinerary → concierge. Each agent's output is
appended to the shared context before the next agent runs:

```yaml
# topologies/linear.yaml
apiVersion: mas/v1
kind: MAS
metadata:
  name: trip-planner-linear

spec:
  agents:
    - id: schedule_agent
      ref: agents/schedule-agent/agent.yaml
      tools: [lookup_schedule]
      skills: [transport-schedule-lookup]
    - id: itinerary_agent
      ref: agents/itinerary-agent/agent.yaml
      tools: [query_graph_database]
      skills: [route-planning]
    - id: concierge_agent
      ref: agents/concierge-agent/agent.yaml
      tools: [get_fares, calc]
      skills: [fare-and-itinerary-assembly]

  routing:
    type: sequential
    entry: schedule_agent
    edges:
      - from: schedule_agent
        to: [itinerary_agent]
      - from: itinerary_agent
        to: [concierge_agent]
```

#### Moderator (`routing.type: llm-routed`)

The canonical moderator-based topology from `ctl/examples/trip-planner/mas.yaml`.
The moderator's LLM decides which specialist to call, in what order, and
how many times:

```yaml
# topologies/moderator.yaml (mirrors ctl/examples/trip-planner/mas.yaml)
spec:
  agents:
    - id: moderator
      ref: agents/moderator/agent.yaml
    - id: schedule_agent
      ref: agents/schedule-agent/agent.yaml
    - id: itinerary_agent
      ref: agents/itinerary-agent/agent.yaml
    - id: concierge_agent
      ref: agents/concierge-agent/agent.yaml

  routing:
    type: llm-routed
    entry: moderator
    nodes:
      - id: moderator
        role: broker
        delegates_to: [schedule_agent, itinerary_agent, concierge_agent]
      - id: schedule_agent
        role: specialist
      # ...
```

### C.2 — The dataset (subset)

For this tutorial we use a 15-item subset of the trip planner benchmark —
5 items from each complexity group:

```json
{
  "items": [
    {"id": 1, "group": "single_agent", "prompt": "What trains go from Celestia to Verdantia?"},
    {"id": 2, "group": "single_agent", "prompt": "How much does the ferry from Luminos to Fortuna cost?"},
    ...
    {"id": 6, "group": "two_agents", "prompt": "Plan a route from Celestia to Pannonia with fare estimates."},
    ...
    {"id": 11, "group": "all_agents", "prompt": "Plan a 3-day trip to Harmonia with budget, activities, and transport."}
  ]
}
```

### C.3 — The experiment manifest

```yaml
# experiment-topology.yaml
experiment:
  name: "t3-topology-comparison"
  version: "v1"
  description: >
    Compare three MAS topologies (single-agent, linear, moderator) on
    15 trip planner prompts. 3 runs per scenario × 15 items = 135 executions.
    Evaluated with MCEv1 AnswerRelevancyMetric.

  default_flavour: local
  applications:
    - manifest: ./mas.yaml
      configs_dir: "topologies"

  scenarios:
    - id: single-agent
      description: "One agent with all tools — no delegation (routing.type: single)"
      tags: [single, baseline]

    - id: linear
      description: "Automaton-driven pipeline: schedule → itinerary → concierge (routing.type: sequential)"
      tags: [linear, sequential]

    - id: moderator
      description: "LLM-routed moderator orchestrates 3 specialists (routing.type: llm-routed)"
      tags: [moderator, broker]

  dataset:
    path: "dataset-topology.json"

  evaluation:
    method: "mce_v1"
    config:
      metrics:
        - AnswerRelevancyMetric
      metric_kwargs:
        model: "gpt-4o"
        threshold: 0.5
        api_key_env: "OPENAI_API_KEY"

  execution:
    n_runs: 3
    parallel_scenarios: 3
    timeout: 300
    pause_between_runs: 1.0
```

### C.4 — Running the experiment

```bash
T03=docs/tutorials/03-experiments-and-analysis

# Validate scaffold (topology overlays optional — see design-space lab for full trip planner)
mas-lab benchmark run "$T03/experiment-topology.yaml" --dry-run

# Full trip-planner topology sweep (larger dataset) — design-space lab:
mas-lab benchmark run labs/design-space.lab/02-topologies/experiment.yaml --progress
```

Expected output:

```
Running MAS benchmark 't3-topology-comparison'
  3 scenarios × 15 items × 3 run(s) = 135 executions

  ✅ [single-agent] item=1 run=1 (8234ms)
  ✅ [single-agent] item=1 run=2 (7891ms)
  ...
  ✅ [moderator] item=15 run=3 (42156ms)

MAS BENCHMARK COMPLETE — t3-topology-comparison
  Total: 135   OK: 135   Errors: 0
```

### C.5 — MCEv1 evaluation

After the benchmark, inspect the run summary and artifacts to compare
topologies (status, latency, traces, and extracted trajectories):

```bash
mas-lab benchmark show last -v
```

Use the generated benchmark output as the source of truth for your run; values
depend on flavour, model, and runtime conditions.

### C.6 — The comparison plot

For the release-safe OSS profile, keep Part C focused on benchmark execution
and artifact inspection:

```bash
mas-lab benchmark show last -v
```

Use the generated benchmark output directory to inspect per-run traces and
status files for each topology.

```
Answer Relevancy by Topology (MCEv1, n=3 runs)

  1.0 ┤
      │                                          ┌───────┐
  0.9 ┤                              ┌───────┐   │       │
      │                              │       │   │  0.89 │
  0.8 ┤              ┌───────┐       │  0.78 │   │   ±   │
      │              │       │       │   ±   │   │ 0.03  │
  0.7 ┤  ┌───────┐   │  0.78 │       │ 0.05  │   │       │
      │  │       │   │   ±   │       │       │   │       │
  0.6 ┤  │  0.71 │   │ 0.04  │       │       │   │       │
      │  │   ±   │   │       │       │       │   │       │
  0.5 ┤  │ 0.08  │   │       │       │       │   │       │
      │  │       │   │       │       │       │   │       │
  0.0 ┼──┴───────┴───┴───────┴───────┴───────┴───┴───────┴──
      single-agent    linear          moderator
```

The ggplot2 code behind this (generated by `mas-lab benchmark analyze`):

```python
from plotnine import *
import pandas as pd

df = pd.read_csv("results.csv")

plot = (
    ggplot(df, aes(x='scenario', y='answer_relevancy', fill='scenario'))
    + geom_boxplot(alpha=0.7)
    + stat_summary(fun_y=np.mean, geom='point', shape='D', size=3)
    + labs(
        title="Answer Relevancy by Topology (MCEv1, n=3 runs)",
        x="Topology",
        y="Answer Relevancy Score"
    )
    + scale_fill_brewer(type='qual', palette='Set2')
    + theme_minimal()
    + theme(
        axis_text_x=element_text(angle=0, hjust=0.5),
        legend_position='none'
    )
)
plot.save("plots/answer_relevancy_by_scenario.svg", width=10, height=6, dpi=150)
```

### C.7 — Interpreting the results

The plot tells a clear story:

- **Single-agent** (0.71 ± 0.08): handles simple queries well, but drops quality
  on complex multi-step trips — one LLM with all tools lacks the focused
  instructions that specialized agents carry.
- **Sequential** (0.78 ± 0.04): the automaton-driven pipeline preserves
  information better (each agent adds to the context), but the fixed
  ordering means the concierge sometimes receives incomplete context from
  earlier stages — no opportunity to loop back.
- **Moderator** (0.89 ± 0.03): the LLM-driven moderator routes each sub-task
  to the most appropriate specialist dynamically. Higher latency (the
  moderator adds a coordination turn), but measurably better answer quality.

The variance (error bars) is also informative: the moderator has the tightest
confidence interval — its quality is more consistent across runs.

### C.8 — Drilling into individual runs

When the aggregate plot reveals a difference, you can drill down:

```bash
# Compare trajectory of same item across topologies (after a benchmark run)
mas-lab plot multilevel-trajectory \
  "$LABS_ROOT/t3-topology-comparison/single-agent/item1/r1/traces/events.jsonl" \
  --format html -o output/single-item1.html

mas-lab plot multilevel-trajectory \
  "$LABS_ROOT/t3-topology-comparison/moderator/item1/r1/traces/events.jsonl" \
  --format html -o output/moderator-item1.html
```

Item 11 (a complex 3-day trip) is where the moderator shines: the trajectory
shows parallel delegation to all 3 specialists, while the single-agent
trajectory shows a long serial chain of tool calls with no specialization.

---

## Key takeaways

1. **`events.jsonl` is the universal artifact**: every run produces one; all analysis starts here
2. **Manual analysis steps (OSS)**: telemetry show → plot trajectory → eval mce
3. **Pipelines make analysis reproducible**: same steps in YAML, with dependencies, run automatically
4. **MCEv1 `AnswerRelevancyMetric`**: LLM-as-judge scores answer quality (0–1 per session)
5. **Grouped plots reveal topology differences**: boxplot by scenario with confidence intervals
6. **Aggregate → drill-down**: start with the comparison plot, then inspect individual trajectories

---

## Infra bundles — declarative service provisioning

An **infra bundle** is a YAML file (analogous to a flavour) that declares the
infrastructure services an experiment needs — OTel collectors, databases,
port-forwards.  Services are started before the benchmark loop and stopped after
via the `service_start` / `service_stop` pipeline steps.

### Anatomy of a bundle

```
labs/my-experiment.lab/infra/
├── local-test.yaml     # Docker-based fake OTel collector
└── staging.yaml        # team staging infra (port-forward or direct)
```

```yaml
# infra/local-test.yaml
services:
  otel-collector:
    description: "Fake OTel collector for local testing"
    backend: docker-compose
    compose_file: "../../../infra/docker-compose.otel.yml"
    env:
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://localhost:4318"
      OTEL_COLLECTOR_DIR: "/private/tmp/mas-otel"
    health_check:
      url: "http://localhost:13133/"
      timeout: 30
```

### Wiring bundle → pipeline

Declare lifecycle steps under `application.pre` / `application.post` and
per-run hooks under `run.post`:

```yaml
experiment:
  default_infra: local-test    # selected when --infra is omitted

  application:
    pre:
      - type: service_start
        name: start-otel
        config:
          service: otel-collector
          health_timeout: 30
    post:
      - type: service_stop
        name: stop-otel
        config:
          service: otel-collector

  run:
    post:
      - type: export_otel
        config:
          events_jsonl: "{events_jsonl}"
          destination: otlp    # reads OTEL_EXPORTER_OTLP_ENDPOINT from env
          service_name: "my-experiment"
          overwrite: true
```

### Selecting the bundle

`--infra` is the CLI flag orthogonal to `--flavour`:

| Flag | Selects |
|------|---------|
| `--flavour local` | LLM / model configuration |
| `--infra local-test` | Infrastructure services (OTel, storage, …) |

```bash
# Local run — Docker collector auto-provisioned
mas-lab benchmark run experiment.yaml --infra local-test --single-run

# to the production collector endpoint)
mas-lab benchmark run experiment.yaml --infra staging

# No infra (destination: json — file output only, no network)
mas-lab benchmark run experiment.yaml
```

### How env vars flow

1. `service_start` calls `ServiceManager.start()` → runs `docker compose up -d`
2. The bundle's `env:` block is injected into the **current process** environment
3. `export_otel` with `destination: otlp` reads `OTEL_EXPORTER_OTLP_ENDPOINT`
   automatically from `os.environ`
4. `service_stop` runs `docker compose down` after all runs complete

> The same mechanism works for **port-forward backends** (k8s services, remote gateways,
> port-forward) — the bundle sets `OTEL_EXPORTER_OTLP_ENDPOINT` to the
> tunnelled address; no change to the experiment YAML is needed.

### Smoke test

The full end-to-end smoke test lives at
`labs/otel-smoke-test.lab/experiment.yaml` and demonstrates all four modes
(JSON file, managed Docker, dry-run, external backend).  Run it with:

```bash
# Mode 2: Docker auto-provisioned
mas-lab benchmark run labs/otel-smoke-test.lab/experiment.yaml \
    --infra local-test --single-run --force

# Inspect spans
cat /private/tmp/mas-otel/traces.jsonl | python3 -m json.tool | head -40
```

---

## Running the experiments

### QA agent analysis (Part A/B)

```bash
T03=docs/tutorials/03-experiments-and-analysis

# Run the QA benchmark (3 scenarios × 2 items × 1 run = 6 executions)
mas-lab benchmark run "$T03/experiment.yaml" --progress

# Run the analysis pipeline
mas-lab benchmark pipeline run "$T03/pipelines/analysis.yaml"
```

### Topology comparison (Part C)

```bash
# Tutorial scaffold (dry-run / small dataset)
mas-lab benchmark run "$T03/experiment-topology.yaml" --dry-run

# Full trip-planner comparison — design-space lab
mas-lab benchmark run labs/design-space.lab/02-topologies/experiment.yaml --progress

# Inspect benchmark metadata and outputs
mas-lab benchmark show last -v
```

---

## File structure

Tutorial artifacts live beside this README:

```
docs/tutorials/03-experiments-and-analysis/
├── README.md
├── agent.yaml                       # Q&A agent (Tutorial 1 style)
├── mas.yaml                         # single-agent MAS wrapper
├── dataset.yaml                     # 2 QA items
├── experiment.yaml                  # Part A/B — pattern sweep
├── experiment-topology.yaml         # Part C scaffold
├── pipelines/analysis.yaml          # post-benchmark analysis
├── overlays/                        # CoT, ReAct, Reflection
├── fixtures/events.jsonl            # offline trace for demo/scenario.yaml
└── demo/scenario.yaml               # CI command replay + expected exit codes
```

Larger experiments: `labs/design-space.lab/` (patterns + topologies).

---

## Next

Use the labs as your base to create additional experiments:

- duplicate an existing `labs/*.lab/experiment.yaml`
- point it to a new dataset or topology overlay
- run `mas-lab benchmark run ...` and compare outputs
