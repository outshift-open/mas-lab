<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Designing experiments

Structure an **experiment manifest** (`experiment.yaml`) for ablations, smoke
validation, and publishable results.

Terms: [glossary.md](../../docs/glossary.md).

## One canonical experiment file

Use CLI flags for smoke — do not fork `experiment-smoke.yaml` unless documented:

```bash
mas-lab benchmark run experiment.yaml --dry-run
mas-lab benchmark run experiment.yaml --limit-scenarios 1 --max-runs 1 --progress
```

## Scenario matrix

Each **scenario** is one column: a setup `id` and which **overlays** apply:

```yaml
experiment:
  scenarios:
    - id: baseline
      overlays: [baseline]
    - id: with-guardrail
      overlays: [baseline, guardrail]
```

Hold **dataset** and `n_runs` constant across scenarios.

Details: [multi-scenario-format.md](multi-scenario-format.md).

## Repeats (`n_runs`)

```yaml
  run:
    n_runs: 3
```

Use `n_runs > 1` when **pipeline steps** report confidence intervals.

## Embedded pipeline for figures

Declare every figure under `pipeline:` in `experiment.yaml`:

```bash
mas-lab benchmark run path/to/experiment.yaml --progress
```

## Example labs

| Study | Lab |
|-------|-----|
| Design patterns | [design-space.lab/01-design-patterns](../../labs/design-space.lab/01-design-patterns/) |
| Topologies | [design-space.lab/02-topologies](../../labs/design-space.lab/02-topologies/) |
| Lifecycle / governance | [lifecycle-control.lab](../../labs/lifecycle-control.lab/) |
| Memory **overlays** | [extensions.lab](../../labs/extensions.lab/) |

Record `experiment.metadata` for publication: [reproducibility.md](../../docs/reproducibility.md).
