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
| Tool (`kind: Tool`) | [tool.md](../manifests/tool.md) · [ToolContract](tool-contract.md) |
| ToolServerRegistry | [infra.md](../manifests/infra.md#toolserverregistry) · [reference](tool-server-registry.md) |
| MAS & workflow | [mas.md](../manifests/mas.md), [workflow.md](../manifests/workflow.md) |
| Overlay | [overlay.md](../manifests/overlay.md) |
| Flavour & environment | [flavour.md](../manifests/flavour.md), [infra.md](../manifests/infra.md) |
| LLM cache middleware | [Guide](../manifests/llm-cache.md) · [Reference](llm-cache.md) |
| Workspace file | [user-config.md](../user-config.md) (paths), [config.yaml reference](config.yaml.md) (fields), [config.schema.yaml](../schemas/config.schema.yaml) |
| Schemas (all) | [Schema index](schemas.md) |
| Contracts | [Contracts](contracts.md) |

---

## Runtime

Execution kernel, contracts, and plugins (`mas-runtime`, `mas-ctl`).

| Topic | Reference |
|-------|-----------|
| Runtime manifests (Agent, MAS, overlay) | [Manifest fields](../manifests/runtime.md) |
| Contracts & Mealy envelope | [Contracts](contracts.md) · [runtime package docs](runtime.md) |
| CLI (`mas-ctl`) | [CLI overview](../cli/index.md) · [mas-ctl options](../cli/mas-ctl.md) |
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
| Lab vs library | [labs-and-libraries.md](../labs-and-libraries.md) |
| Library discovery | [library-discovery.md](../library-discovery.md) |
| Bench design & steps | [Lab package docs](lab.md) |
| Package map | [libraries.md](../libraries.md) |

---

## See also

- [User guide](../user-guide.md) — install and day-to-day workflows
- [CLI](../cli/index.md) · [mas-ctl options](../cli/mas-ctl.md)
- [config.yaml](config.yaml.md) — workspace / user YAML fields
- [Tutorials](../tutorials/index.md) — hands-on tutorials (agents → teams → experiments)
- [Paper labs](../paper/index.md) — reproduce Section 5 of the article
- [Web UI](../ui/index.md) — design and inspect in the browser
