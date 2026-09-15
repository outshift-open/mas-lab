# library-ioc-motivation

A set of **reproduction experiments** on the **`sre-triage`** app. Each experiment runs a
baseline scenario plus per-challenge variants (`CR-1`, `DC-2`, `CC-3`, `DR-1`, …) over a
seed incident query, `n_runs` times, producing agent traces you can inspect in the
Experiment views.

## Scope — content-only, no install

This library ships **content only**: the app, its overlays, the experiments, and a dataset —
all plain YAML read from the filesystem. There's no Python to install, so the controller
**discovers and displays it, and runs its experiments, with no `uv install`**.

## Layout

```
library.yaml                          # kind: Library — metadata only
apps/sre-triage/                      # SRE incident-triage MAS (pins vertex_ai/gemini-2.5-flash)
apps/sre-triage/overlays/             # per-challenge variants (baseline + *-debate variants)
datasets/sre-queries.yaml
experiments/ioc-sre-reproduction.yaml # centralized: sre-orchestrator delegates
experiments/ioc-sre-debate.yaml       # decentralized: staged debate
```

## Usage

Run an experiment from the Experiments page:

| experiment             | coordination                                  |
| ---------------------- | --------------------------------------------- |
| `ioc-sre-reproduction` | centralized (sre-orchestrator delegates)      |
| `ioc-sre-debate`       | decentralized (`deterministic_staged_debate`) |

Each produces `baseline + challenge × n_runs` traces, viewable in the Experiment
results views.

> **N matters.** `n_runs: 1` is a coin flip; use 5 as a minimum, and 20+ for a stable
> baseline — a single app can swing a result run-to-run from model + agent stochasticity.
