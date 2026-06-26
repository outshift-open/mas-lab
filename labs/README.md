<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Labs

**Labs** (`*.lab/`) hold **experiment** manifests for paper §5. Each
`experiment.yaml` lists **scenarios**, a **dataset**, and an **embedded pipeline**
that builds figures from **`events.jsonl`** logs.

Terms: [glossary.md](../docs/glossary.md).

## Generate figures

```bash
mas-lab benchmark run labs/<name>.lab/experiment.yaml --progress
```

Quickstart: [lab/docs/labs-quickstart.md](../lab/docs/labs-quickstart.md) ·
Paper map: [docs/paper/index.md](../docs/paper/index.md).

## Labs

| Lab | Paper § | Focus |
|-----|---------|-------|
| [design-space.lab](design-space.lab/) | §5.1 | Design patterns + topologies |
| [lifecycle-control.lab](lifecycle-control.lab/) | §5.2 | Governance **overlays** across lifecycle |
| [extensions.lab](extensions.lab/) | §5.3 | Memory **overlays** — [README](extensions.lab/README.md) |

## Run all

```bash
task reproduce
```

## Output paths

| `experiment.name` | Typical path |
|-------------------|--------------|
| `lab1-exp1.1-design-patterns-qa` | `~/.mas/labs/lab1-exp1.1-design-patterns-qa/` |
| `lab1-exp1.2-topologies-trip-planner` | `~/.mas/labs/lab1-exp1.2-topologies-trip-planner/` |
| `lifecycle-control` | `~/.mas/labs/lifecycle-control/lifecycle-control/` |
| `memory-extension-reproducibility` | `~/.mas/labs/memory-extension-reproducibility/` |

```bash
mas-lab benchmark show last plots
```

## Extend

[lab/docs/labs-going-further.md](../lab/docs/labs-going-further.md).

## See also

- [docs/paper/index.md](../docs/paper/index.md)
- [cli/observability.md](../docs/cli/observability.md)
