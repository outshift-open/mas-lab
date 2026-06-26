<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Lab 1 — Design Space Exploration

**Paper §**: §5.1  
**Tutorial**: [docs/tutorials/03-experiments-and-analysis/](../../docs/tutorials/03-experiments-and-analysis/)

This lab answers the question: *can I explore reasoning strategies and coordination topologies by editing a YAML file, without touching agent code?*

Two experiments run against the same pipeline:

| Exp | What varies | Agent | Dataset | Scenarios |
|-----|-------------|-------|---------|-----------|
| [1.1 — design-patterns-qa](01-design-patterns/) | Design pattern overlay | Single QA agent | 100 reasoning queries | CoT, ReAct, Plan-Execute, Reflection, ToT |
| [1.2 — topologies-trip-planner](02-topologies/) | Topology overlay | 4-agent trip-planner | 100 trip-planner prompts | parallel, linear-pipeline, moderator-broker, supervised, verifier |

Both measure goal success rate (GSR), answer relevancy (AR), and session latency under identical conditions — only the declared overlay changes between scenarios.

---

## Running the experiments

```bash
# From repository root
# Prerequisites: uv, Python 3.11+, and an OpenAI-compatible endpoint in env.
# See docs/reproducibility.md for full setup.

mas-lab benchmark run labs/design-space.lab/01-design-patterns/experiment.yaml --progress
mas-lab benchmark run labs/design-space.lab/02-topologies/experiment.yaml --progress

# Quick smoke (first 5 items per scenario):
mas-lab benchmark run labs/design-space.lab/01-design-patterns/experiment.yaml --max-items 5 --progress
```

Results and figures are written to `~/.mas/labs/<experiment-name>/results/` (see `mas-lab config`).

---

## Exp 1.1 — Design patterns on a QA agent

**What it tests.** Five reasoning strategy overlays applied to the same single-agent QA binary on the same 100-item dataset. The only difference between runs is the `design_pattern` field in the overlay.

**Scenarios.**

| Scenario ID | Pattern | Behaviour |
|-------------|---------|-----------|
| `pattern-cot` | Chain-of-Thought | Agent reasons step-by-step before answering |
| `pattern-react` | ReAct | Agent interleaves reasoning and tool calls |
| `pattern-plan-execute` | Plan-and-Execute | Agent builds a plan then executes it |
| `pattern-reflection` | Reflection | Agent critiques and revises its own output |
| `pattern-tree-of-thoughts` | Tree-of-Thoughts | Agent explores multiple reasoning branches |

**Key finding (from paper §5.1).** Plan-and-Execute reaches near-perfect text quality (AR ≈ 0.999) but near-zero task completion (GSR ≈ 0.030): it produces plausible-looking answers that do not actually solve the task. This dissociation is invisible from a single metric and only detectable when AR and GSR are measured under identical conditions. ReAct and Reflection sit at the Pareto frontier of quality and latency.

**Metrics.** Answer Relevancy (AR), Goal Success Rate (GSR), session latency (s).

**Output.** `results/figure-01-overhead-quality.png` — scatter plot with 2D confidence intervals, AR/GSR on y-axis, latency on x-axis, one point per (pattern, metric) combination.

---

## Exp 1.2 — Coordination topologies on the trip-planner MAS

**What it tests.** Five topology overlays applied to the same 4-agent trip-planner MAS on the same 100-item benchmark. The agent code is byte-identical across scenarios.

**Scenarios.**

| Scenario ID | Topology | Control flow |
|-------------|----------|-------------|
| `topo-parallel` | Parallel | Moderator fans out to all specialists concurrently |
| `topo-linear-pipeline` | Linear pipeline | Agents execute in a fixed sequential chain |
| `topo-moderator-broker` | Moderator-broker | Dynamic delegation to the right specialist |
| `topo-supervised` | Supervised | Supervisor reviews and approves each agent output |
| `topo-verifier` | Verifier | A dedicated verifier checks all agent outputs |

**Key finding (from paper §5.1).** Whether parallel fan-out improves task completion over a moderator-broker baseline depends on the task and dataset — MAS-Lab measures this rigorously. The experiment provides the infrastructure to make this comparison; no prior claim is made about which topology wins.

**Metrics.** Goal Success Rate (GSR), session latency (s).

**Output.** `results/figure-02-overhead-quality.png` — same format as Exp 1.1 but filtering on GSR only; topology scenarios on color axis.

---

## Reproducing from scratch

The experiments are fully self-contained: `experiment.yaml` declares everything needed to re-run (manifest, dataset path, overlays, pipeline). Key files:

```
01-design-patterns/
├── experiment.yaml          # Scenarios, pipeline, metadata
└── overlays/                # One YAML per design pattern

02-topologies/
├── experiment.yaml
└── overlays/                # One YAML per topology
```

Datasets resolve from the **`samples`** library locator (see `library.yaml` ids):

- `qa-reasoning-queries-100` (Exp 1.1)
- `trip-planner-benchmark-100` — Dataset A (Exp 1.2)
- `trip-planner-benchmark` — Dataset B (trip-planner benchmark, released in library-samples)

MAS apps resolve via **`mas.app`** registry (`library.yaml` → `app:` in experiment):

- `qa-agent` → `apps/qa-mas/mas.yaml` (Exp 1.1)
- `trip-planner` → `apps/trip-planner/mas.yaml` (Exp 1.2)

For details on metadata capture, cross-model re-evaluation, and output validation see [docs/reproducibility.md](../../docs/reproducibility.md).
