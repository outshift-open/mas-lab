<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# MAS manifest (`kind: MAS`)

**Package:** `mas-runtime` · **Schema:** `mas.schema.yaml` · **apiVersion:** `mas/v1`

A **MAS** (multi-agent system) manifest (`mas.yaml`) declares a team of **agents** and the
**workflow** between them (who delegates to whom). **Experiments** usually point at a MAS
app plus **scenario** **overlays** that change topology or governance.

**Terms:** [glossary.md](../glossary.md) · Hub: [README.md](README.md).

Declares multi-agent composition: participants, control flow, and system-level hooks.

---

## Responsibilities

| Area | `spec` fields | Role |
|------|---------------|------|
| Participants | `agency.agents[]` | `id` + `ref` to agent manifests (or inline definitions) |
| Topology | `workflow` | `entry`, `nodes`, `delegates_to`, `edges` — see [topology-and-workflow.md](topology-and-workflow.md) |
| Transport | `transport` | High-level comm mode (`local`, `agent-remote`, emulation flags) |
| Shared tools | `tools_ref` | Default logical tool-set (resolved via infra ToolRegistry) |
| Infra wiring | `infra_refs[]` | Paths to `infra/v1` manifests / bundles |
| Memory artifacts | `memory_stores` | Episodic / semantic / procedural store paths |
| Telemetry | `telemetry.path` | Default events.jsonl location |
| System intent | `intent` (top-level) | Summary for emulation / agent cards |

Inter-agent **delegation graph** lives here; per-agent **delegation policy** lives on
Agent `collaboration`.

---

## Mealy product view

```text
User input → workflow.entry agent → (delegation edges) → specialist agents
Each agent: own design_pattern Mealy machine + shared bus/transport
```

See [workflow.md](workflow.md) for the workflow manifest.

---

## Overlays

Topology-switching overlays replace `spec.patch.workflow` or `spec.patch.agents` — see
Scenario overlays are declared in [experiment.md](experiment.md); patch files
are documented in [overlay.md](overlay.md).

---

## Schema source

`GET /api/schemas/mas` · file `runtime/.../mas.schema.yaml`

---

## See also

- [Agent manifest](agent.md)
- [Tutorial: creating a MAS](../tutorials/02-creating-a-mas/README.md)
- [Topology, workflow, and routing](topology-and-workflow.md)
- [Workflow manifest](workflow.md)
