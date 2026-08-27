<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Design: Experiment overlays

**Status**: Draft  
**Branch**: `feat/experiment-overlays`  
**Relates to**: §5b FT3 (flavour/infra/overlay boundary)

---

## Problem

`experiment.yaml` mixes two distinct concerns:

**Spec** (invariant — *what* to measure):
```yaml
scenarios: [baseline, design-pattern, ...]
dataset: { path: hybrid-regression.yaml }
design: { mode: coupled, couplings: [...] }
```

**Execution properties** (operational — *how* to run):
```yaml
execution:
  parallel_scenarios: 2
  timeout: 600
  emulation:
    runtime:
      cache: disabled    # ← this buried option caused silent re-execution of ALL experiments
```

The mixing means:
1. A `cache: disabled` buried deep in the YAML silently bypasses the trace cache,
   causing every `benchmark run` to make fresh LLM calls — even when debugging a
   pipeline step.
2. The CLI has no way to override `emulation.*` properties — it cannot say "use
   the cache" without editing the YAML.
3. Different run environments (CI fast-pass, local dev, full benchmark) require
   separate experiment files or in-place edits, both of which pollute history.

**Principle violated**: CLI should always have the last word.  
In every other MAS Lab surface (`mas-ctl chat`, `mas-ctl run`, `benchmark run`)
the CLI overrides YAML.  `emulation.runtime.cache` is the only exception.

---

## Proposed solution: experiment overlays

Parallel to agent/MAS overlays, an **experiment overlay** amends the experiment
spec at load time without modifying the base YAML.

```
experiment.yaml          ← the spec (scenarios, dataset, design)
execution/
  local-dev.yaml         ← cache=content-addressed, parallel=4, timeout=120
  ci-fast.yaml           ← n_runs=1, single scenario, mock LLM
  full-benchmark.yaml    ← n_runs=10, all scenarios, live LLM
```

CLI composition:

```bash
# Local dev (fast iteration on pipeline)
mas-lab benchmark run experiment.yaml -x execution/local-dev.yaml

# CI gate
mas-lab benchmark run experiment.yaml -x execution/ci-fast.yaml --max-runs 1

# Full benchmark
mas-lab benchmark run experiment.yaml -x execution/full-benchmark.yaml
```

The `-x`/`--experiment-overlay` flag (new) applies the overlay before resolving
any other CLI overrides.  CLI flags (`--max-runs`, `--set`, etc.) still win over
the overlay.

---

## Overlay schema (draft)

An experiment overlay is a YAML file with the same keys as `experiment:` but
all fields optional.  Deep merge semantics (same as agent overlays):
- scalar → replace
- dict → recursive merge
- list → replace (explicit `$append`/`$op` for incremental updates)

```yaml
# execution/local-dev.yaml
apiVersion: mas/v1
kind: ExperimentOverlay
metadata:
  name: local-dev
spec:
  execution:
    parallel_scenarios: 4
    timeout: 120
    emulation:
      runtime:
        cache: content-addressed   # never disable in local dev
  run:
    n_runs: 1                      # override default 3
```

```yaml
# execution/ci-fast.yaml
apiVersion: mas/v1
kind: ExperimentOverlay
metadata:
  name: ci-fast
spec:
  dataset:
    limit: 1                       # first item only
  execution:
    parallel_scenarios: 1
    emulation:
      runtime:
        cache: content-addressed
  run:
    n_runs: 1
```

---

## CLI override chain (precedence, lowest → highest)

```
experiment.yaml defaults
  → experiment overlay (-x / --experiment-overlay)
    → --infra <bundle>
      → --flavour <name>
        → --max-runs N
          → --set KEY=VALUE       (highest, always wins)
```

This matches the agent/MAS override chain and makes the system predictable.

---

## Alternative: `--set` on experiment keys

A lighter alternative (no new overlay format): extend `--set` to apply to
experiment-level keys, not just pipeline steps:

```bash
mas-lab benchmark run experiment.yaml \
  --set experiment.execution.emulation.runtime.cache=content-addressed \
  --set experiment.run.n_runs=1
```

This is lower implementation cost but less ergonomic for multi-key overrides.
A `--set-experiment KEY=VALUE` flag (separate namespace from `--set`) avoids
ambiguity with pipeline step names.

---

## Related prior art

- Agent overlays (`overlays/*.yaml`) — same deep-merge pattern
- `--flavour` — selects deployment posture for the LLM layer
- `--infra` — selects infrastructure bundle (OTel, storage)
- `emulation:` block — execution properties that should be overlay-able

The gap: `--flavour` and `--infra` both have CLI flags; `emulation.*` does not.

---

## Implementation sketch

1. `ExperimentOverlay` manifest kind (new, trivial schema)
2. `load_experiment_with_overlays(yaml_path, overlay_paths)` in `experiment_base.py`
3. `-x` / `--experiment-overlay` flag on `benchmark run`
4. Precedence: overlays applied in order, then CLI overrides on top
5. `--dry-run` prints the merged config (not just the base) so the effective
   state is auditable

Estimated scope: small (the merge machinery already exists for agent overlays).

---

## Why this matters for reproducibility

An experiment YAML describes the *hypothesis being tested*.  It should be stable
across environments.  The execution properties (cache, parallelism, LLM mock vs
live) are *infrastructure concerns* that vary by context.

Mixing them in one file means the experiment YAML changes when the environment
changes — making git history less meaningful and reproducibility harder.

Separating them (via overlays or `--set`) makes each concern independently
versionable and auditable.
