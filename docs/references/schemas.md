<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Schema index

YAML and JSON schemas used by `mas-ctl validate`, `mas-lab check`, and the
benchmark UI. Files live under [`docs/schemas/`](../schemas/).

Human-readable field docs are in [Specifications](index.md#specifications).

---

## Workspace & project

| Schema | Purpose |
| --- | --- |
| [`config.schema.yaml`](../schemas/config.schema.yaml) | Root `config.yaml` — defaults, flavour, infra refs, `manifest_libraries:` |
| [`library.schema.yaml`](../schemas/library.schema.yaml) | `kind: Library` (`library.yaml`) — [labs-and-libraries.md](../labs-and-libraries.md) |
| [`deployment.schema.yaml`](../schemas/deployment.schema.yaml) | Deployment / placement descriptors |
| [`runtime-profile.schema.yaml`](../schemas/runtime-profile.schema.yaml) | Runtime profile flags (governance, observability) |
| [`placement-plan.schema.yaml`](../schemas/placement-plan.schema.yaml) | Component placement plan |
| [`effective-bind.schema.yaml`](../schemas/effective-bind.schema.yaml) | Resolved binding after overlay merge |
| [`memory-seed.schema.yaml`](../schemas/memory-seed.schema.yaml) | Dataset memory seed files |
| [`checkpoint.schema.yaml`](../schemas/checkpoint.schema.yaml) | Execution checkpoint payloads |

---

## Runtime manifests

Top-level kinds (see [manifest reference](../manifests/README.md)):

| Schema | `kind` / role |
| --- | --- |
| [`runtime/agent.schema.yaml`](../schemas/runtime/agent.schema.yaml) | `Agent` |
| [`runtime/mas.schema.yaml`](../schemas/runtime/mas.schema.yaml) | `MAS` |
| [`runtime/workflow.schema.yaml`](../schemas/runtime/workflow.schema.yaml) | `Workflow` |
| [`runtime/overlay.schema.yaml`](../schemas/runtime/overlay.schema.yaml) | `Overlay` |
| [`runtime/flavour.schema.yaml`](../schemas/runtime/flavour.schema.yaml) | `Flavour` |
| [`runtime/infra.schema.yaml`](../schemas/runtime/infra.schema.yaml) | Infra bundle / middleware / ToolServerRegistry — [infra.md](../manifests/infra.md) · [reference](tool-server-registry.md) |
| [`runtime/tool.schema.yaml`](../schemas/runtime/tool.schema.yaml) | Tool definition — [tool.md](../manifests/tool.md) |
| [`runtime/fragments/infra-tool-server.schema.yaml`](../schemas/runtime/fragments/infra-tool-server.schema.yaml) | Infra `tool_servers[]` item — [tool-server-registry.md](tool-server-registry.md) |
| [`runtime/tool_bundle.schema.yaml`](../schemas/runtime/tool_bundle.schema.yaml) | Bundled tools |
| [`runtime/prompt_bundle.schema.yaml`](../schemas/runtime/prompt_bundle.schema.yaml) | Prompt bundles |

Shared fragments under [`runtime/fragments/`](../schemas/runtime/fragments/) —
bindings, workflow nodes/edges, policy rules, design-pattern config, etc.

---

## Lab & benchmarks

| Schema | Purpose |
| --- | --- |
| [`lab/experiment.schema.yaml`](../schemas/lab/experiment.schema.yaml) | `experiment.yaml` |
| [`lab/dataset.schema.yaml`](../schemas/lab/dataset.schema.yaml) | Dataset manifest |
| [`lab/pipeline.schema.yaml`](../schemas/lab/pipeline.schema.yaml) | Pipeline step definitions |
| [`lab/lab.schema.yaml`](../schemas/lab/lab.schema.yaml) | Lab folder metadata |
| [`lab/lab-config.schema.yaml`](../schemas/lab/lab-config.schema.yaml) | Lab config, including `lab.libraries` |
| [`lab/run-input.schema.yaml`](../schemas/lab/run-input.schema.yaml) | Per-run inputs |
| [`lab/pipeline-manifest.schema.json`](../schemas/lab/pipeline-manifest.schema.json) | Serialized pipeline manifest |
| [`lab/artefacts/run_info.schema.json`](../schemas/lab/artefacts/run_info.schema.json) | Run metadata artefact |
| [`lab/artefacts/metrics.schema.json`](../schemas/lab/artefacts/metrics.schema.json) | Metrics artefact |

---

## Contracts, components & evaluation

| Schema | Purpose |
| --- | --- |
| [`contracts-registry.yaml`](../schemas/contracts-registry.yaml) | Plugin contract registry (see [Contracts](contracts.md)) |
| [`component-registry.yaml`](../schemas/component-registry.yaml) | Component / plugin registry |
| [`evaluation-envelope.schema.yaml`](../schemas/evaluation-envelope.schema.yaml) | Evaluation result envelope |

---

## Examples

Sample overlays and bindings under [`schemas/examples/`](../schemas/examples/):

- [`overlays/live-llm.yaml`](../schemas/examples/overlays/live-llm.yaml)
- [`overlays/mcp-localhost.yaml`](../schemas/examples/overlays/mcp-localhost.yaml)
- [`infra/mcp-localhost.yaml`](../schemas/examples/infra/mcp-localhost.yaml)
- [`tools/annotated.tool.yaml`](../schemas/examples/tools/annotated.tool.yaml)

Plus `*.example.yaml` siblings next to deployment, placement, memory-seed, and
runtime-profile schemas.
