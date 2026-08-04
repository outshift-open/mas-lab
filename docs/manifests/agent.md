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
| Peer delegation | MAS `workflow` (when embedded in a MAS) | `delegates_to` graph + `workflow.type`; executed by the entry agent's own `design_pattern` (ReAct tool loop) — see [mas.md](mas.md) |
| Context window | `context_manager` | Stack / sliding-window / summarising |
| Prompt / role | `description`, `context` | `description` → delegation tools; `context.*` → system prompt |
| Models | `models[]` | LLM routing (ids, temperature, max_tokens) |
| Tools | `tools`, `tools_ref` | ToolContract surface |
| Skills | `skills`, `context_manager.skills` | Context facets + `consult_skills` |
| Memory | `memory`, `memory_seed` | Stores + startup seeds |
| Working memory | `working_memory.persistent` | Cross-turn buffer survives repeat delegate calls within one session (default `true`) — see below |
| Kernel plugins | `plugins[]`, `governance[]`, `observability[]` | Governance and observability on Mealy envelope chokepoints (not a hook plane) |
| Execution bounds | `execution` | Timeouts, retries |

---

## Delegation

**Who** an agent may delegate to is declared on the **MAS** manifest, not on the agent alone:

| Concern | Manifest | Field |
|---------|----------|-------|
| Delegation graph (peers) | MAS | `spec.workflow.nodes[].delegates_to`, `workflow.entry` |
| Workflow driver | MAS | `spec.workflow.type` — `dynamic` (LLM picks peers), `sequential`, or `single` |
| Per-peer tool text | Agent | `spec.description` — surfaced on `delegate_to_<id>` tools for the entry agent |

When `workflow.type` is **dynamic**, the entry agent's LLM receives one OpenAI tool per allowed peer:
`delegate_to_<agent_id>` with a `task` argument. `mas-ctl run-mas` executes those calls over the
materialized in-process CommBus via the default `LlmDelegator` plugin. There is no separate
delegation-transport plugin binding on the agent — *how* peer delegation executes is the entry
agent's own `design_pattern` (the ReAct tool loop dispatching `delegate_to_*` tool calls), the same
contract that drives its own reasoning.

See [topology-and-workflow.md](topology-and-workflow.md) and [mas.md](mas.md).

---

## Working memory across delegate calls

A delegated agent's `RuntimeInstance` is materialized once per MAS run and reused for every
`delegate_to_<agent_id>` call in that run — so by default a sub-agent already sees its own prior
exchange on the second call: `moderator` asks for "Foo", gets it, then says "add Bar" without
repeating context, and the sub-agent still has "Foo" in its committed history.

**`spec.working_memory.persistent`** (default `true`) makes this explicit and controllable per
agent, keyed by `(session_id, agent_id)` in an in-process registry rather than relying on Python
object reuse:

```yaml
working_memory:
  persistent: true   # default — continue this agent's history across delegate calls in-session
```

Set `persistent: false` for a sub-agent that must be stateless per call (e.g. a formatter or
translator that should never see a previous, unrelated delegation's turns) — its committed history
is cleared before every delegate call even though the underlying instance is reused.

**Overlays can set this too** (`spec.patch.working_memory.persistent` on an `Overlay` targeting
`kind: Agent`) — useful to flip a shared agent manifest's default per deployment/experiment without
forking it.

**`context_id`** — the delegating agent's LLM may optionally pass `context_id` as an extra argument
on `delegate_to_<agent_id>`, alongside `task`. When given, it selects an independent working-memory
bucket for that peer instead of the session's default one — e.g. a moderator running two unrelated
conversations with the same specialist (`context_id: "trip-paris"` vs. `"trip-tokyo"`) within one
session, with neither leaking into the other. Omit it (the common case) to use the session's
default bucket, as described above.

This is in-memory and scoped to one mas-ctl session/run — it does not persist across separate CLI
invocations. Cross-process persistence (`spec.memory.persistence`) is a tracked follow-up.

**`spec.working_memory.compaction`** — how much of the committed history to keep as it grows. A
facade over `spec.context_manager`/`CMFactory` (set `context_manager` directly instead for
lower-level control — it takes precedence if both are set):

```yaml
working_memory:
  compaction:
    strategy: keep_recent   # keep_recent (default, no LLM call) | sliding_window | summarize
    max_messages: 200       # keep_recent
    window_size: 20         # sliding_window
    summary_threshold: 4000 # summarize
    keep_turns: 10          # summarize — recent exchanges kept verbatim alongside the summary
```

`summarize` calls an LLM (using this agent's own resolved model) to compress older turns into one
summary block; it degrades to `keep_recent` rather than failing if no live model is available.
`keep_recent`/`sliding_window` never spend a model call. See
`docs/design/working-memory-compaction.md` for the full design and why the two dead schema surfaces
this replaces were removed.

---

## Composition

- **Standalone:** single `agent.yaml` via `mas-ctl chat agent.yaml` (or `mas-ctl run-mas` when embedded in a MAS).
- **In a MAS:** referenced by `MAS.spec.agency.agents[].ref`.
- **Inline:** full agent spec embedded in MAS (studio export) — same fields under agent entry.
- **Overridden:** `Overlay.spec.patch.agents.<id>` or global `design_pattern` / `tools: {"$op": {"remove": [...]}}`.

---

## Reference forms

```yaml
design_pattern:
  ref: module://my_pkg.patterns.MyCoT   # plugin locator
  # or type: react
skills:
  - triage-protocol
  - "@sre-skills/memory-protocol"       # library id
description: "Telemetry analyst. Call for latency baselines and error rates."
context:
  role: |
    You are a telemetry analyst…
```

Inline prompt file reference:

```yaml
context:
  role:
    ref: "./prompts/broker.md"
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
