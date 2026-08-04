<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Lab 1 — Experiment 1.3: Collaboration Patterns

Factorial comparison of **topology** and **moderator design pattern** on the trip-planner
benchmark. Six scenarios = 2 topologies × 3 moderator patterns, all using the same agents,
tools, and dataset.

---

## Topologies

All topologies are declared in `library-samples/apps/trip-planner/mas-topologies/`.

| Topology | File | Entry agent | Delegation |
|----------|------|-------------|------------|
| **single-agent** | `single-agent.mas.yaml` | `generalist` | none — one agent with all tools |
| **linear-pipeline** | `linear-pipeline.mas.yaml` | `schedule_agent` | deterministic chain: schedule → itinerary → concierge |
| **moderator-broker** | `moderator-broker.mas.yaml` | `moderator` | hub-and-spoke, dynamic delegation to specialists |
| **parallel** | `parallel.mas.yaml` | `moderator` | parallel fan-out (`dispatch: parallel`) to all specialists |
| **supervised** | `supervised.mas.yaml` | `moderator` | broker with bounded review delegation |
| **verifier** | `verifier.mas.yaml` | `moderator` | moderator → itinerary proposes → schedule verifies |

### Workflow diagrams

```
single-agent          linear-pipeline              moderator-broker / parallel
─────────────         ──────────────────────       ──────────────────────────────
generalist            schedule_agent               moderator
 (all tools)            │                           ├── schedule_agent
                         ▼                           ├── itinerary_agent
                       itinerary_agent              └── concierge_agent
                         │                         (parallel: simultaneous)
                         ▼
                       concierge_agent

supervised (bounded)  verifier
─────────────────────  ─────────────────────
moderator              moderator
 ├── schedule_agent     ├── itinerary_agent (propose)
 ├── itinerary_agent   └── schedule_agent  (verify)
 └── concierge_agent
```

---

## Collaboration pattern overlays

Overlays in `overlays/` compose a topology with a moderator design pattern. They patch
`spec.workflow` (topology) and `spec.agents.moderator.design_pattern` (pattern):

| Overlay | Topology | Moderator pattern |
|---------|----------|-------------------|
| `collab-broker-react.yaml` | moderator-broker | ReAct |
| `collab-broker-cot.yaml` | moderator-broker | Chain-of-Thought |
| `collab-broker-reflection.yaml` | moderator-broker | Reflection |
| `collab-parallel-react.yaml` | parallel fan-out | ReAct |
| `collab-parallel-cot.yaml` | parallel fan-out | Chain-of-Thought |
| `collab-parallel-reflection.yaml` | parallel fan-out | Reflection |
| `example-sequential-linear.yaml` | sequential chain | (no moderator pattern) |

---

## Quick start

### 1 — Run a single topology interactively

```bash
# Moderator-broker topology (live LLM)
mas-ctl run-mas library-samples/apps/trip-planner/mas-topologies/moderator-broker.mas.yaml \
  -q "What trains run from Celestia to Verdantia?"

# Parallel topology
mas-ctl run-mas library-samples/apps/trip-planner/mas-topologies/parallel.mas.yaml \
  -q "What trains run from Celestia to Verdantia?"

# Linear pipeline (no moderator)
mas-ctl run-mas library-samples/apps/trip-planner/mas-topologies/linear-pipeline.mas.yaml \
  -q "What trains run from Celestia to Verdantia?"

# Offline/mock (no API key needed)
mas-ctl run-mas library-samples/apps/trip-planner/mas-topologies/moderator-broker.mas.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/mock-llm.yaml \
  -q "What trains run from Celestia to Verdantia?"
```

### 2 — Apply a collaboration pattern overlay

Overlays compose the topology and moderator behaviour in one step:

```bash
# Moderator-broker + ReAct (overlay drives both topology and pattern)
mas-ctl run-mas library-samples/apps/trip-planner/mas.yaml \
  -o labs/design-space.lab/03-collaboration-patterns/overlays/collab-broker-react.yaml \
  -q "What trains run from Celestia to Verdantia?"

# Parallel fan-out + CoT
mas-ctl run-mas library-samples/apps/trip-planner/mas.yaml \
  -o labs/design-space.lab/03-collaboration-patterns/overlays/collab-parallel-cot.yaml \
  -q "What trains run from Celestia to Verdantia?"

# Sequential linear chain
mas-ctl run-mas library-samples/apps/trip-planner/mas.yaml \
  -o labs/design-space.lab/03-collaboration-patterns/overlays/example-sequential-linear.yaml \
  -q "What trains run from Celestia to Verdantia?"
```

### 3 — Run the benchmark

**Smoke run** (10 items, 1 run per scenario — validates the whole pipeline quickly):

```bash
mas-lab benchmark run \
  labs/design-space.lab/03-collaboration-patterns/experiment-smoke.yaml \
  --progress
```

**Full factorial experiment** (6 scenarios × full dataset):

```bash
mas-lab benchmark run \
  labs/design-space.lab/03-collaboration-patterns/experiment.yaml \
  --progress
```

The pipeline produces:
- `results/ci_summary.csv` — mean quality and latency per scenario with 95% CI
- `results/figure-03-collab-overhead-quality.png` — quality vs overhead scatter
- `results/figure-03-collab-llm-calls.png` — LLM call counts per topology

---

## Plotting traces

After running a topology (with `mas-ctl run-mas` or `mas-lab benchmark run`), traces are
written as `events.jsonl`. Use the plot commands below to visualise them.

### Communication flow (agent-to-agent graph)

Renders the actual delegation graph observed during a run:

```bash
# From a specific events.jsonl
mas-lab plot communication-flow path/to/traces/events.jsonl -o flow.html

# From a benchmark run directory (auto-discovers events.jsonl)
mas-lab plot communication-flow \
  ~/.local/share/mas/labs/lab1-exp1.3-collaboration-patterns-trip-planner/collab-broker-react/item1/r1 \
  -o broker-react-flow.html

# Mermaid format (paste into any Markdown renderer)
mas-lab plot communication-flow \
  path/to/traces/events.jsonl --format mermaid -o flow.md
```

The output shows which agents actually communicated and in which direction — useful for
verifying that the topology overlay was applied correctly.

### Message-graph swimlane diagram

Renders a detailed per-turn swimlane with delegation edges, tool calls, and iteration
bands. Requires a normalised `kg.json` (produced by the benchmark pipeline):

```bash
# From a kg.json (produced after a benchmark run)
mas-lab plot message-graph path/to/kg.json -o swimlane.svg
mas-lab plot message-graph path/to/kg.json --format html -o swimlane.html

# From a benchmark run directory (discovers kg.json automatically)
mas-lab plot message-graph \
  ~/.local/share/mas/labs/lab1-exp1.3-collaboration-patterns-trip-planner/collab-broker-react/item1/r1
```

### Comparing topologies side-by-side

Run benchmark + plot for each scenario in one loop:

```bash
for scenario in collab-broker-react collab-parallel-react; do
  mas-lab benchmark run \
    labs/design-space.lab/03-collaboration-patterns/experiment-smoke.yaml \
    --filter-scenario "$scenario" \
    -o /tmp/collab-out/"$scenario" \
    --progress
  mas-lab plot communication-flow /tmp/collab-out/"$scenario" \
    -o /tmp/collab-out/"$scenario"/flow.html
done
```

---

## Experiment design

```
  Topology axis             Pattern axis
  ─────────────             ─────────────
  moderator-broker    ×     ReAct
  parallel fan-out    ×     CoT
                      ×     Reflection
  ──────────────────────────────────────
  6 scenarios total
```

Each scenario overlay patches:
1. `spec.workflow` — defines delegation graph (topology)
2. `spec.agents.moderator.design_pattern` — sets the reasoning loop

The base MAS manifest (`library-samples/apps/trip-planner/mas.yaml`) declares agents and
tools; overlays compose the collaboration structure on top without touching agent
definitions.

---

## Files

```
03-collaboration-patterns/
├── README.md                          this file
├── experiment.yaml                    full factorial benchmark (6 scenarios)
├── experiment-smoke.yaml              smoke run (10 items, 1 run)
├── experiment-sequential-demo.yaml    sequential chain demo
├── experiment-topology-definitions-smoke.yaml
├── scenario-interpretation.csv        ground-truth labels for eval
├── lib/steps/scenario_interpretation.py
└── overlays/
    ├── collab-broker-cot.yaml         moderator-broker + CoT
    ├── collab-broker-react.yaml       moderator-broker + ReAct
    ├── collab-broker-reflection.yaml  moderator-broker + Reflection
    ├── collab-parallel-cot.yaml       parallel + CoT
    ├── collab-parallel-react.yaml     parallel + ReAct
    ├── collab-parallel-reflection.yaml parallel + Reflection
    └── example-sequential-linear.yaml deterministic linear chain
```

Base MAS topologies (shared across labs):

```
library-samples/apps/trip-planner/mas-topologies/
├── single-agent.mas.yaml
├── linear-pipeline.mas.yaml
├── moderator-broker.mas.yaml
├── parallel.mas.yaml
├── supervised.mas.yaml
└── verifier.mas.yaml
```
