<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# References

Complete reference material for MAS Lab: YAML manifests, JSON/YAML schemas,
runtime contracts, and lab benchmarking. New to the vocabulary? Start with the
[glossary](../glossary.md).

---

## Specifications

Declarative YAML kinds and how they compose.

| Topic | Reference |
|-------|-----------|
| Overview & composition | [Manifest overview](../manifests/README.md) |
| Agent | [agent.md](../manifests/agent.md) |
| MAS & workflow | [mas.md](../manifests/mas.md), [workflow.md](../manifests/workflow.md) |
| Overlay | [overlay.md](../manifests/overlay.md) |
| Flavour & environment | [flavour.md](../manifests/flavour.md), [infra.md](../manifests/infra.md) |
| Workspace file | [user-config.md](../user-config.md), [config.schema.yaml](../schemas/config.schema.yaml) |
| Schemas (all) | [Schema index](schemas.md) |
| Contracts | [Contracts](contracts.md) |

---

## Runtime

Execution kernel, contracts, and plugins (`mas-runtime`, `mas-ctl`).

| Topic | Reference |
|-------|-----------|
| Runtime manifests (Agent, MAS, overlay) | [Manifest fields](../manifests/runtime.md) |
| Contracts & Mealy envelope | [Contracts](contracts.md) · [runtime package docs](runtime.md) |
| CLI (`mas-ctl`, `mas-runtime`) | [ctl user guide](https://github.com/outshift-open/mas-lab/blob/main/ctl/docs/user-guide.md) |
| **Web UI** | [ui/index.md](../ui/index.md) |
| Run logs | [Observability](../cli/observability.md) |

---

## Lab & benchmarks

Experiments, datasets, pipelines, and analysis (`mas-lab`).

| Topic | Reference |
|-------|-----------|
| Experiment manifest | [experiment.md](../manifests/experiment.md) |
| Dataset | [dataset.md](../manifests/dataset.md) |
| Pipeline steps | [pipeline.md](../manifests/pipeline.md) |
| Interactive lab demo | [lab.md](../manifests/lab.md) |
| Bench design & steps | [Lab package docs](lab.md) |
| Package map | [libraries.md](../libraries.md) |

---

## See also

- [User guide](../user-guide.md) — install and day-to-day workflows
- [Tutorials](../tutorials/index.md) — hands-on tutorials (agents → teams → experiments)
- [Paper labs](../paper/index.md) — reproduce Section 5 of the article
- [Web UI](../ui/index.md) — design and inspect in the browser
