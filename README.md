<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# MAS-Lab

A **specification-driven foundation** for building multi-agent systems that are
testable, reproducible, observable, and governable from design to production.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)

Modern multi-agent systems are easy to prototype, but hard to trust at scale.
MAS-Lab helps developers, enterprises, and researchers move from prompt-glued
prototypes to engineered agentic systems — with explicit specifications, runtime
contracts, reproducible experiments, and built-in observability.

- **Documentation site:** [outshift-open.github.io/mas-lab](https://outshift-open.github.io/mas-lab/)
- **Release overview:** [blog post](docs/blog/posts/2026-06-17-v0-1-release/)

## Get started

**[Tutorial 0 — Environment setup](docs/tutorials/00-environment-setup/README.md)** — install once (Docker or developer path), then:

| Path | Link |
|------|------|
| Tutorials | [docs/tutorials/](docs/tutorials/index.md) |
| Web UI demo | [docs/ui/index.md](docs/ui/index.md) |
| Paper labs | [docs/paper/index.md](docs/paper/index.md) |

Full site content mirrors [`docs/`](docs/) — see [docs/index.md](docs/index.md) for the full introduction.

## The problem

Prototype demos are easy; production-grade trust is not. Prompts, tools,
orchestration, and control are often interwoven, so behavior is hard to reproduce,
debug, or govern. MAS-Lab separates **intent**, **execution**, **observability**,
and **governance** through a shared specification and runtime model.

## What MAS-Lab provides

- Declarative MAS specifications (agents, tools, workflows, contracts)
- Runtime enforcement at system boundaries
- Governance and experimentation overlays
- Observability, replay, and benchmark pipelines
- Three reproducible [paper labs](docs/paper/index.md) (Section 5)

## Who it is for

- **Developers** — specs instead of glue code; [tutorials](docs/tutorials/index.md)
- **Enterprises** — overlays for policy, audit, and control; [user guide](docs/user-guide.md)
- **Researchers** — reproducible campaigns; [paper labs](docs/paper/index.md)

## Packages

The headline packages:

| Package | Role |
| --- | --- |
| `mas-runtime` | Agent runtime — contracts, plugins, design patterns |
| `mas-ctl` | Orchestration — `chat`, `run-mas`, `validate` |
| `mas-lab` | Meta-package — benchmarks, pipelines, telemetry, UI controller |
| `mas-library-standard` | Flavours, overlays, infra bundles |

`mas-lab` is a meta-package that installs the lab components (`mas-lab-core`,
`mas-lab-bench`, `mas-lab-controller`, `mas-lab-content`).
Additional libraries ship alongside it (`mas-library-eval`, `mas-library-lab`,
`mas-library-samples`).

See [docs/libraries.md](docs/libraries.md) for the library model and
[docs/packages-reference.md](docs/packages-reference.md) for the complete,
auto-generated package list with dependencies and extras.

## Supported versions

Security fixes are applied to the latest release on the `main` branch.

| Version | Supported |
| --- | --- |
| latest on `main` | yes |
| older tagged releases | best effort |

## Citing this work

If you use MAS-Lab in research or publications, cite the
[MAS-Lab article](docs/paper/index.md) — not only this repository.

## Contributing

Contributions are what make the open source community such an amazing place to
learn, inspire, and create. Any contributions you make are **greatly
appreciated**. For detailed contributing guidelines, please see
[CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md)


## License

Distributed under the `Apache 2.0` License. See [LICENSE](LICENSE) for more
information.
