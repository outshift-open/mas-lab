<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Agent manifest (`kind: Agent`)

**Package:** `mas-runtime` · **Schema:** `agent.schema.yaml` · **apiVersion:** `mas/v1`

An **agent** manifest (`agent.yaml`) declares one LLM actor: tools, skills, design
pattern, plugins, and **observability** settings. A **MAS** manifest references one or
more agents; **overlays** patch agents without duplicating the base file.

---

## Plugin bindings

Singleton slots accept a **plugin name** or `{type, ref, params}`. List slots
use `[{plugin_name: {params}}]`. Full rules: [plugin-bindings.md](plugin-bindings.md).

```yaml
spec:
  design_pattern: cot          # ≡ {type: cot}
  context_manager: stack       # ≡ {type: stack}
  assembler: assembler         # omit for the same default
```

## Spec field reference

Every `spec` key from `agent.schema.yaml`. **Default** is what omitting the
field does. **Equivalent** is the object `mas-ctl compile` writes. Bindings:
[plugin-bindings.md](plugin-bindings.md). To see this table as one real
`mas-ctl compile` output instead of a hand-written summary:
[Compiled agent defaults](../references/defaults.md).

| Field | Default | Notes |
|-------|---------|-------|
| `description` | *(required)* | Routing one-liner for `delegate_to_*` tools. Not the system prompt. |
| `context` | `{}` | Named system-prompt chunks (`role`, `intent`, …). String, `{ref}`, or fragment list. |
| `params` | `{}` | Free-form strings for middleware / sidecars. Not kernel config. |
| `models[]` | `[{id: main, model: <defaults.model>}]` | `temperature` 0.7, `max_tokens` 2000 (completion reserve), `context_window` 128000. |
| `design_pattern` | `react` | Shorthand `design_pattern: cot` ≡ `{type: cot}`. Compile fills `params.max_steps: 512`, `max_cot_pass: 1`, `parallel: true`. |
| `assembler` | `assembler` | Builds `messages[]`. Compile fills `emit_segments: true`, `always_reassemble: false`. |
| `context_manager` | `summarising` | History plugin. Sub-plugin `params.summarizer` (`llm` \| `drop`). See [context-assembly.md](context-assembly.md). |
| `working_memory.persistent` | `true` | Committed buffer survives delegate calls in-session. |
| `working_memory.compaction` | *(unset)* | Sugar for `context_manager` (LLM view + stored-log cap). Ignored if `context_manager` is set. |
| `memory` | flavour | Shorthand `semantic` or full `types` / `persistence` / `search` object. |
| `memory_seed` | `[]` | Documents indexed at startup. |
| `skills` | `[]` | Skill names or `@library/name`. |
| `tools` | `[]` | Semantic name, `{ref}`, `{kind: system, name}`, or inline `module_path`. |
| `tools_ref` | `null` | Logical tool-set name for infra ToolRegistry. |
| `providers` | `[]` | Tool-provider claims. Empty → local plugin owns `spec.tools`. |
| `behavior.share_reasoning` | `false` | Optional `reasoning_context` on send_to_caller. |
| `behavior.delegation_style` | `typed` | `delegate_to_<id>` from MAS topology. |
| `governance` | `[]` | List slot. Bare id or `{plugin_name: {params}}`. |
| `observability` | `[]` | List slot (`native`, `otel`). Flavour/CLI may attach native. |
| `context_sources` | `[]` | Skill-engine list (`native`, `adk`, `langchain`). |
| `control` | `{}` | Control-plane plugin configs keyed by id. |
| `llm` | `{}` | Deprecated model shim. Prefer `models[]`. |

### `design_pattern` (default equivalent)

```yaml
spec:
  design_pattern:
    type: react
    params:
      max_steps: 512
      max_cot_pass: 1
      parallel: true
```

Shipped ids: `react`, `cot`, `single_pass`, `introspection`, `plan_execute`,
`tree_of_thoughts`, `deterministic_single`, `deterministic_linear`,
`deterministic_parallel`. Same default params; `cot` / `introspection` /
`tree_of_thoughts` consume `max_cot_pass`.

### `context_manager` + `summarizer` (default equivalent)

```yaml
spec:
  context_manager:
    type: summarising
    params:
      keep_turns: 10
      hysteresis_ratio: 0.2
      summarizer: llm          # registry type summarizer; drop = discard older turns
      summary_threshold: 126000
      working_memory_messages: 20
      trimmer:
        max_tokens: 128000
        reserve_tokens: 2000
```

The summarising manager **has strategy code** (recency pin + hysteresis cache)
and **composes** a summarizer sub-plugin. `stack` and `sliding-window` have
no summarizer.

### `assembler` (default equivalent)

```yaml
spec:
  assembler:
    type: assembler
    params:
      emit_segments: true
      always_reassemble: false
```

## Responsibilities

| Area | `spec` fields | Trajectory impact |
|------|---------------|-------------------|
| Reasoning loop | `design_pattern` | Selects DesignPatternContract (ReAct, CoT, …) — intra-agent δ transitions |
| Peer delegation | MAS `workflow` (when embedded in a MAS) | `delegates_to` graph + `workflow.type`; executed by the entry agent's own `design_pattern` (ReAct tool loop) — see [mas.md](mas.md) |
| Prompt assembly | `assembler` | default `assembler` (ContextAssemblerPlugin) — [context-assembly.md](context-assembly.md) · [plugin-bindings.md](plugin-bindings.md) |
| Context window | `context_manager` | default `summarising` (last `keep_turns` verbatim; `summarizer: llm` or `drop`) / sliding-window / stack — [context-assembly.md](context-assembly.md) |
| Prompt / role | `description`, `context` | `description` → delegation tools; `context.*` → system prompt |
| Models | `models[]` | LLM routing (ids, temperature, max_tokens completion, context_window) |
| Tools | `tools`, `tools_ref`, `providers` | [ToolContract](../references/tool-contract.md) · [tool.md](tool.md) · [ToolServerRegistry](../references/tool-server-registry.md) |
| Skills | `skills` | Context facet (catalog) + `activate_skill`/`read_skill_file` tools |
| Memory | `memory`, `memory_seed` | Stores + startup seeds |
| Working memory | `working_memory.persistent` | Cross-turn buffer survives repeat delegate calls within one session (default `true`) — see below |
| Kernel plugins | `governance[]`, `observability[]` | Governance and observability on Mealy envelope chokepoints (not a hook plane) |
| Engine / flavour | workspace `runtime_refs` / flavour | Mocking, LLM cache, engine queue — not an agent spec field; see [execution.md](execution.md) |

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
duplicating the agent file.

**`context_id`** — the delegating agent's LLM may optionally pass `context_id` as an extra argument
on `delegate_to_<agent_id>`, alongside `task`. When given, it selects an independent working-memory
bucket for that peer instead of the session's default one — e.g. a moderator running two unrelated
conversations with the same specialist (`context_id: "trip-paris"` vs. `"trip-tokyo"`) within one
session, with neither leaking into the other. Omit it (the common case) to use the session's
default bucket, as described above.

This is in-memory and scoped to one mas-ctl session/run — it does not persist across separate CLI
invocations. Cross-process persistence (`spec.memory.persistence`) is a tracked follow-up.

**`spec.working_memory.compaction`** is **sugar for `spec.context_manager`**, not a
second engine and not a cache of working memory.

- **Committed history is rewritten at turn commit** to the same recency cap
  (`keep_turns` / `max_turns` / `max_messages`). Folded prefix data is dropped
  from `committed_messages` and conversation chunks so snapshots stay bounded.
- **The LLM view** is the same policy: each call, `context_manager.manage_history`
  builds the payload (drop or summarize older turns).
- **The cache is hysteresis on the context-manager instance** (summarising plugin):
  after a summary, new turns stay verbatim until the managed payload grows
  `hysteresis_ratio` (default 0.2) past budget. That avoids a summarizer LLM call
  on every in-turn step without mutating working memory.
- **Working memory** is the live tool round (this turn) plus the optional
  persistent committed buffer (`working_memory.persistent`).

Prefer `spec.context_manager` (what compile emits). If both are set, `context_manager` wins.

```yaml
# equivalent to context_manager: {type: stack, params: {max_messages: 200}}
working_memory:
  compaction:
    strategy: keep_recent
    max_messages: 200
```

---

## Tool providers

`spec.providers[]` claims **which** plugin owns **which** names. Invocation is
[`call_tool(name, arguments)`](../references/tool-contract.md). Optional
advertise fields live on [`kind: Tool`](tool.md).

Connection URL, transport, headers, pagination, and list-cache policy belong
on infra [`ToolServerRegistry`](../references/tool-server-registry.md). Match
`providers[].name` to `tool_servers[].id`. Overlay `providers[]` may set
`url`; when both overlay and infra set a key, the overlay value is used.

```yaml
providers:
  - name: localhost-mcp-tools   # matches infra tool_servers[].id
    kind: mcp
    tools: "*"                  # discover at runtime init
```

With no `providers`, the default local plugin owns `spec.tools`. Once any
external plugin is present, unclaimed names are an error unless reintroduced
with `kind: local`.

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

Array of fragments — resolved and joined with newlines. Lets an overlay
append (or remove) one fragment via `context: {role: {"$op": {"add": [...]}}}`
without restating the rest of the prompt (see overlay.md#merge-semantics):

```yaml
context:
  role:
    - "You are a telemetry analyst…"
    - ref: "./prompts/escalation.md"
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

- [Runtime engine](runtime-engine.md) — queue depth, cache/stream policy, parallel tool dispatch (workspace `runtime_refs`, not on agents)
- [execution.md](execution.md) — removed `spec.execution` on agents (migration pointer)
- [MAS manifest](mas.md) — topology and transport
- [Overlay manifest](overlay.md) — overrides
- [Tool manifest](tool.md) — `kind: Tool` advertise fields
- [ToolContract](../references/tool-contract.md) — `call_tool(name, arguments)`
- [Infra ToolServerRegistry](infra.md#toolserverregistry) — remote URL / transport · [reference](../references/tool-server-registry.md)
- [plugin-bindings.md](plugin-bindings.md) — string shorthand vs `{type, params}` vs list slots
- [Compiled agent defaults](../references/defaults.md) — a minimal manifest, fully expanded
- [Tutorial: building an agent](../tutorials/01-building-an-agent/README.md)

