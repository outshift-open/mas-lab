<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Manifest mapping

How YAML manifest fields bind to runtime contracts and kernel modules.

---

## Agent manifest (`kind: Agent`)

| Manifest path | Binds to |
|---------------|----------|
| `spec.model` | Flavour + `ModelAccessContract` |
| `spec.tools[]` | `ToolContract` plugins |
| `spec.plugins[]` | Registry entries (dp, cm, gov, …) |
| `spec.design_pattern` | DP plugin id (`react`, `plan_execute`, …) |
| `spec.context` | Context budget, facets |
| `governance.policies` | Governance policy engine |
| `observability` | Events file, OTel export |

Resolution: `mas.ctl.runtime_cli.load_merged_agent_manifest` →
`instantiate_runtime`.

---

## MAS manifest (`kind: MAS`)

| Manifest path | Binds to |
|---------------|----------|
| `spec.agents[]` | Agent manifests + placement |
| `spec.workflow` | `WorkflowContract` driver |
| `spec.scenarios` | Overlay paths for bench |

Resolution: `mas.ctl.compose` → `run-mas`.

---

## Experiment manifest (`experiment.yaml`)

| Field | Binds to |
|-------|----------|
| `dataset` | Bench dataset loader |
| `scenarios` | Overlay matrix |
| `run` | `n_runs`, concurrency |
| `pipeline.steps` | `mas.lab.benchmark.pipeline` step types |

Entry: `mas-lab benchmark run`.

---

## Flavour and infra

| Artifact | Role |
|----------|------|
| `flavour/*.yaml` | Model id, infra ref, log level |
| `infra/*.yaml` | Proxy URL, allowed models, interceptors |
| `mas-workspace.yaml` | `MAS_INFRA_REFS`, default flavour |

Schema: [docs/schemas/mas-workspace.schema.yaml](../../../docs/schemas/mas-workspace.schema.yaml).

---

## Related

- [DESIGN_SPACE.md](DESIGN_SPACE.md)
- [../../../docs/manifests/README.md](../../../docs/manifests/README.md)
