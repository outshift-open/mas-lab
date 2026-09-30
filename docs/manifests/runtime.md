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
| ---------- | ------------- | ---------------- |
| Agent | `agent.schema.yaml` | [agent.md](agent.md) · [plugin-bindings.md](plugin-bindings.md) · [context-assembly.md](context-assembly.md) |
| MAS | `mas.schema.yaml` | [mas.md](mas.md) |
| Overlay | `overlay.schema.yaml` | [overlay.md](overlay.md) |
| Workflow topology | `workflow.schema.yaml` | [mas.md — Standalone workflow manifest](mas.md#standalone-workflow-manifest-kind-workflow) |
| Flavour | `flavour.schema.yaml` | [flavour.md](flavour.md) |
| Infrastructure | `infra.schema.yaml` | [infra.md](infra.md) |
| RuntimeEngine | `runtime-engine.schema.yaml` | [runtime-engine.md](runtime-engine.md) |
| Tool | `tool.schema.yaml` | [tool.md](tool.md) |
| ToolBundle | `tool_bundle.schema.yaml` | [tool.md](tool.md) |
| PromptBundle | `prompt_bundle.schema.yaml` | [PromptBundle](#prompt-bundle) |
| Workspace | `workspace.py` + docs | [user-config.md](../user-config.md) |

API id (controller): `agent`, `mas`, `overlay`, `workflow`, `flavour`, `tool`, `tool-bundle`, `prompt-bundle`.

---

## Tool family

| Kind | Purpose |
| ------ | --------- |
| `Tool` | Single tool definition (parameters, implementation ref) |
| `ToolBundle` | Bundle of tool entries |
| `PromptBundle` | Named prompts for `context.*` `{ref: ...}` / `@lib#key` |

Agents reference tools by **semantic name** or `tools[].ref` to a `kind: Tool`
manifest ([tool.md](tool.md)). Infra `ToolServerRegistry` maps remote endpoints
([infra.md](infra.md#toolserverregistry)). Invocation is
[`ToolContract.call_tool`](../references/tool-contract.md).

## PromptBundle

`kind: PromptBundle` uses [`prompt_bundle.schema.yaml`](../schemas/runtime/prompt_bundle.schema.yaml).
It requires `metadata.name` and `spec.entries`; each entry requires `type`
(`system`, `few-shot`, or `intent`) and may contain `text`, `items`, or `tags`.
The schema does not conditionally require `text` or `items` based on `type`.

## ToolBundle

`kind: ToolBundle` uses [`tool_bundle.schema.yaml`](../schemas/runtime/tool_bundle.schema.yaml).
It requires `metadata.name` and `spec.tools`. Each entry requires `description`;
optional fields include `module_path`, `class_name`, `input_schema`,
`output_schema`, `idempotent`, and `timeout_seconds`.

---

## Separation rules (config hygiene)

Enforced by `mas-lab check-config` and flavour separation validators:

These rules define **semantic ownership**, not a required file layout. Where a
field's schema allows it, the same resource can be declared inline, referenced
by a filesystem/library path, or selected by a catalog id; these forms resolve
to the same kind-specific data without moving the concern to another owner.
For example, `MAS.spec.agency.agents[]` accepts inline Agent documents or
`ref`s, `Agent.spec.tools[]` accepts semantic names, Tool/ToolBundle refs, or
inline implementations, and `experiment.application` accepts a manifest path
or a registered app id. They are equivalent in ownership and resolved intent,
not interchangeable in syntax; see [writing-manifests.md](writing-manifests.md)
for the forms accepted by each field.

| Concern | Belongs in |
| --------- | ------------ |
| Model id, temperature | `Agent.spec.models` |
| API base, API keys | `infra/v1` `LLMProxy` (via workspace `infra_refs` or CLI `--infra-ref`) |
| Remote tool URL / headers / pagination | `infra/v1` `ToolServerRegistry` |
| Tool advertise contract (description, parameters, protocol hints) | `kind: Tool` or ToolBundle entry; agents bind it through `spec.tools[]` |
| Topology, delegation graph | `MAS.spec.workflow` |
| Protocol / OTel defaults | `Flavour` |
| Scenario-specific behaviour | `Overlay` |

---

## Contracts and plugins

Formal **contracts** (tool invocation, delegation, governance) are implemented
in `mas-runtime`. In manifests, agent and MAS behavior is declared via:

- `spec.design_pattern` — intra-agent Mealy step selection (`DesignPatternPlugin` via registry); peer
  delegation (`delegate_to_*` tool calls) runs through this same contract — there is no separate
  delegation-transport plugin binding on the agent
- `spec.governance[]`, `spec.observability[]`, `spec.control` and `spec.context_sources` — schema-declared governance, observation, control, and context-source bindings
- `MAS.spec.workflow` — topology (`entry`, `nodes`, `delegates_to`, `dispatch`); standalone `kind: Workflow` has a separate `workflow/v1` schema with `edges`

There is no `spec.plugins[]`, `spec.workflow.type`, or `spec.workflow.plugin` field
in the current Agent/MAS schemas. See the topology, workflow, and routing section in [mas.md](mas.md#topology-workflow-and-routing).

Authoring detail: [agent.md](agent.md#delegation) · [mas.md](mas.md).

---

## Further reading

- [agent.md](agent.md)
- [mas.md](mas.md)
- [infra.md](infra.md)
- [tool.md](tool.md)
- [ToolContract](../references/tool-contract.md)
- [ToolServerRegistry](../references/tool-server-registry.md)
