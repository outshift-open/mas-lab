<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# MAS-Lab paper

*MAS-Lab: A Specification-Driven Validation Framework for Reliable Multi-Agent
Systems*

The article introduces the specification-driven model behind MAS-Lab. **Section 5**
reports experiments that are reproduced in this repository as three runnable labs.

---

## What you can reproduce

| Lab | Paper section | What it explores |
|-----|---------------|------------------|
| `design-space.lab` | §5.1 | Design patterns and team topologies |
| `lifecycle-control.lab` | §5.2 | Governance and lifecycle control |
| `extensions.lab` | §5.3 | Memory and context overlays |

Source under [`labs/`](https://github.com/outshift-open/mas-lab/tree/main/labs) in the repository.

Each lab is a single benchmark experiment. Run it, and MAS-Lab produces the
figures and tables reported in the paper — charts, metrics, and comparison
reports — without separate plotting scripts.

Hands-on introduction: [Tutorial 3 — Run an experiment](tutorials/03-experiments-and-analysis/README.md).

---

## Quick reproduction

After [Tutorial 0](tutorials/00-environment-setup/README.md) (install and LLM
access), from the repository root:

```bash
task reproduce
```

This runs all Section 5 experiments in sequence. To run one lab:

```bash
mas-lab benchmark run labs/design-space.lab/01-design-patterns/experiment.yaml --progress
```

Completed runs are cached — re-running refreshes reports without repeating LLM
calls when inputs are unchanged. See [User configuration](user-config.md) for
output locations.

---

## Cite MAS-Lab

When you use the framework, benchmarks, or methodology, cite the paper — not
only this Git Repository.

**Authors:** Jordan Augé, Giovanna Carofiglio, Giulio Grassi, Jacques Samain
(Cisco Systems / Outshift)

**arXiv:** link will be posted here when the preprint is public. Watch
[outshift-open/mas-lab](https://github.com/outshift-open/mas-lab) releases or this
documentation site.

```bibtex
@article{maslab2026,
  title   = {{MAS-Lab}: A Specification-Driven Validation Framework for Reliable Multi-Agent Systems},
  author  = {Aug{\'e}, Jordan and Carofiglio, Giovanna and Grassi, Giulio and Samain, Jacques},
  year    = {2026},
  note    = {arXiv preprint, forthcoming},
  url     = {https://github.com/outshift-open/mas-lab}
}
```

Update `note` and `url` with the arXiv identifier when available.

---

## See also

- [Home](index.md)
- [Tutorial 0 — Environment setup](tutorials/00-environment-setup/README.md)
- [Tutorials](tutorials/index.md)
- [References](references/index.md)
- [Blog](blog/index.md)
