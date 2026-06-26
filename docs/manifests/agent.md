<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Agent manifest (`kind: Agent`)

**Package:** `mas-runtime` · **Schema:** `agent.schema.yaml` · **apiVersion:** `mas/v1`

An **agent** manifest (`agent.yaml`) declares one LLM actor: tools, skills, design
pattern, plugins, and **observability** settings. A **MAS** manifest references one or
more agents; **overlays** patch agents without duplicating the base file.

**Terms:** [glossary.md](../glossary.md) · Hub: [README.md](README.md).

Declares one runtime participant: how it reasons, what it can call, what context it
sees, and which plugins hook its execution.

---

## Responsibilities

| Area | `spec` fields | Trajectory impact |
|------|---------------|-------------------|
| Reasoning loop | `design_pattern` | Selects DesignPatternContract (ReAct, CoT, …) — intra-agent δ transitions |
| Delegation | `collaboration` | How to pick among `delegates_to` peers (topology is on MAS) |
| Context window | `context_manager` | Stack / sliding-window / summarising |
| Prompt / role | `role`, `context`, `intent` | System prompt assembly |
| Models | `models[]` | LLM routing (ids, temperature, max_tokens) |
| Tools | `tools`, `tools_ref` | ToolContract surface |
| Skills | `skills`, `context_manager.skills` | Context facets + `consult_skills` |
| Memory | `memory`, `memory_seed` | Stores + startup seeds |
| Kernel plugins | `plugins[]`, `governance[]`, `observability[]` | Governance and observability on Mealy envelope chokepoints (not a hook plane) |
| Execution bounds | `execution` | Timeouts, retries |

---

## Composition

- **Standalone:** single `agent.yaml` via `mas-ctl chat agent.yaml` (or `mas-ctl run-mas` when embedded in a MAS).
- **In a MAS:** referenced by `MAS.spec.agency.agents[].ref`.
- **Inline:** full agent spec embedded in MAS (studio export) — same fields under agent entry.
- **Overridden:** `Overlay.spec.patch.agents.<id>` or global `design_pattern` / `tools_remove`.

---

## Reference forms

```yaml
design_pattern:
  ref: module://my_pkg.patterns.MyCoT   # plugin locator
  # or type: react
skills:
  - triage-protocol
  - "@sre-skills/memory-protocol"       # library id
role:
  instructions_ref: "./prompts/broker.md"
```

---

## Schema source

```bash
# From installed package
python -c "from mas.lab.schemas.paths import runtime_schema_dir; print(runtime_schema_dir() / 'agent.schema.yaml')"

# From Web UI / controller (default port 8090)
curl http://localhost:8090/api/schemas/agent
```

---

## See also

- [MAS manifest](mas.md) — topology and transport
- [Overlay manifest](overlay.md) — overrides
- [Tutorial: building an agent](../tutorials/01-building-an-agent/README.md)
- [Design patterns](agent.md#design-pattern) — `spec.design_pattern` on agents
