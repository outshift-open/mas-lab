<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Runtime manifests (`mas-runtime`)

Execution manifests consumed by **mas-runtime** and **mas-ctl**. Authoritative JSON
Schemas: [`docs/schemas/runtime/`](../schemas/runtime/).

Validated by `mas-ctl validate` (agents, MAS, overlays) and `mas-lab validate`
(experiments, pipelines, lab configs).

---

## Manifest index

| Manifest | Schema file | Reference page |
|----------|-------------|----------------|
| Agent | `agent.schema.yaml` | [agent.md](agent.md) |
| MAS | `mas.schema.yaml` | [mas.md](mas.md) |
| Overlay | `overlay.schema.yaml` | [overlay.md](overlay.md) |
| Workflow topology | `workflow.schema.yaml` | [workflow.md](workflow.md) |
| Flavour | `flavour.schema.yaml` | [flavour.md](flavour.md) |
| Infrastructure | Python models (`infra_manifest.py`) | [infra.md](infra.md) |
| Tool | `tool.schema.yaml` | below |
| ToolBundle | `tool_bundle.schema.yaml` | below |
| PromptBundle | `prompt_bundle.schema.yaml` | below |
| Workspace | `workspace.py` + docs | [user-config.md](../user-config.md) |

API id (controller): `agent`, `mas`, `overlay`, `workflow`, `flavour`, `tool`, `tool-bundle`, `prompt-bundle`.

---

## Tool family

| Kind | Purpose |
|------|---------|
| `Tool` | Single tool definition (parameters, implementation ref) |
| `ToolBundle` | Bundle of tool entries |
| `PromptBundle` | Named prompts for `context.*` `{ref: ...}` / `@lib#key` |

Agents reference tools by **semantic name** or inline definition; infra `ToolRegistry` maps
logical ids to JSON index files.

---

## Separation rules (config hygiene)

Enforced by `mas-lab check-config` and flavour separation validators:

| Concern | Belongs in |
|---------|------------|
| Model id, temperature | `Agent.spec.models` |
| API base, API keys | `infra/v1` `LLMProxy` (via `infra_refs`) |
| Topology, delegation graph | `MAS.spec.workflow` |
| Protocol / OTel defaults | `Flavour` |
| Scenario-specific behaviour | `Overlay` |

---

## Contracts and plugins

Formal **contracts** (hook interception, protocol validation, governance) are
implemented in `mas-runtime`. In manifests, trajectory-shaping logic is declared via:

- `spec.design_pattern` — intra-agent Mealy step selection (`DesignPatternPlugin` via registry)
- `spec.collaboration` — *design:* `DelegationContract` plugin binding (how peer delegation executes). *This release:* omit or `type: none`; peer tools come from MAS `workflow.delegates_to` when `workflow.type` is `dynamic`; ctl wires default `LlmDelegator` at `run-mas`
- `spec.plugins[]` — hook-plane plugins (module_path + class_name)
- `MAS.spec.workflow` — topology (`entry`, `delegates_to`, `type`) and ctl workflow driver (dynamic ReAct vs `SequentialWorkflow`)

`MAS.spec.workflow.plugin` (custom `WorkflowContract` registration) is a **design target** — not
resolved in OSS; see [topology-and-workflow.md](topology-and-workflow.md).

Authoring detail: [agent.md](agent.md#delegation-and-collaboration) · [mas.md](mas.md).

---

## Further reading

- [agent.md](agent.md)
- [mas.md](mas.md)
- [infra.md](infra.md)
