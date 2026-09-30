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

---

## Top-level fields

| Field | Type | Required | Description |
| ------- | ------ | ---------- | ------------- |
| `apiVersion` | `string` | yes | Must be `mas/v1`. |
| `kind` | `string` | yes | Must be `MAS`. |
| `metadata` | object | yes | Identity and defaults. See [`metadata` fields](#metadata-fields). |
| `spec` | object | yes | Runtime behaviour. See [`spec` fields](#spec-fields). |
| `intent` | object | no | What this system knows and can do. See [`intent`](#intent). Prefer this top-level form when authoring a base manifest directly (overlays patch via `spec.intent`). |

Extension properties (`x-*`) are allowed at the top level and are ignored by the runtime.

**Minimal example:**

```yaml
apiVersion: mas/v1
kind: MAS
metadata:
  name: trip-planner
spec:
  agency:
    agents:
      - id: broker
        ref: ./agents/broker.yaml
      - id: flights
        ref: ./agents/flights.yaml
  workflow:
    entry: broker
    nodes:
      - id: broker
        delegates_to: [flights]
      - id: flights
```

---

## `metadata` fields

| Field | Type | Required | Default | Description |
| ------- | ------ | ---------- | --------- | ------------- |
| `name` | `string` | **yes** | — | Unique MAS identifier. Used in run output paths and agent URNs. |
| `version` | `string` | no | `"0.1.0"` | Semver string (`major.minor.patch`). |
| `description` | `string` | no | `""` | Human-readable description. |
| `tags` | `string[]` | no | `[]` | Free-form tags for filtering and grouping. |
| `default_flavour` | `string` | no | `"local"` | Name of the flavour to use when none is specified on the CLI. |

Extension properties (`x-*`) are allowed and ignored by the runtime.

---

## `spec` fields

No fields are required; an empty `spec: {}` is valid.

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `models` | `ModelEntry[]` | `[]` | Default model slots inherited by agents; `model: any` resolves through experiment and workspace defaults. See [`ModelEntry`](#modelentry). |
| `agency` | object | — | Participants and delegation targets. See [`Agency`](#agency). |
| `agents` | array | `[]` | Short-form agent references or inline Agent definitions, equivalent to `agency.agents` on a base manifest. In a MAS overlay, `spec.patch.agents` accepts per-agent patches or `$op` collection operations. |
| `workflow` | object | — | Entry point and delegation graph. See [`Workflow`](#workflow). |
| `transport` | object | — | Communication protocol config. See [`Transport`](#transport). |
| `framework` | object | — | Framework surface adapter. See [`Framework`](#framework). |
| `tools_ref` | `string` \| null | `null` | MAS-level logical tool-set name resolved by the infra `ToolRegistry`. No paths or extensions. |
| `memory_stores` | object | — | Named memory store artifact paths. See [`MemoryStores`](#memorystores). |
| `telemetry` | object | — | Telemetry output config. See [`Telemetry`](#telemetry). |
| `params` | `object` | `{}` | Free-form string key/value params for lab/benchmark tooling — not consumed by the runtime kernel directly. |
| `capabilities` | `object` | `{}` | Free-form capability declarations read by manifest loading — not consumed by the runtime kernel directly. |
| `intent` | object | `{}` | Overlay-patchable intent block. Prefer the top-level `intent` field when authoring a base manifest. |
| `middleware` | — | `null` | Reserved for future use. |

---

## Sub-schemas

### `intent`

_Used by:_ top-level `intent` (and `spec.intent` for overlays)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `summary` | `string` | `""` | Short description of what this system knows and can do. Used in emulation and agent cards. |

**Example:**

```yaml
intent:
  summary: "Books travel: flights, hotels, and itineraries."
```

---

### ModelEntry

_Used by:_ `spec.models[]`

| Field | Type | Required | Default | Description |
| ------- | ------ | ---------- | --------- | ------------- |
| `model` | `string` | **yes** | — | LiteLLM model id or `any` to inherit the resolved model slot. |
| `id` | `string` | no | `main` | Model slot identifier. |
| `temperature` | `number` | no | — | Sampling temperature, from `0` to `2`. |
| `max_tokens` | `integer` | no | — | Completion token limit; must be at least `1`. |
| `context_window` | `integer` | no | — | Model context-window size; must be at least `1`. |

---

### Agency

_Used by:_ `spec.agency`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `agents` | `AgentEntry[]` | `[]` | Ordered list of agent participants. See [`AgentEntry`](#agententry). |

---

### AgentEntry

`spec.agency.agents[]` and the short-form `spec.agents[]` have different
reference requirements:

#### Agency entry (`spec.agency.agents[]`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | **yes** | Logical agent id used by workflow nodes and delegation targets. |
| `ref` | `string` | no | Path to an Agent manifest relative to the MAS manifest. Omit for an external agent resolved through an infra Application endpoint. |

#### Short-form entry (`spec.agents[]`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ref` | `string` | **yes** | Path to an Agent manifest. |
| `id` | `string` | no | Logical agent id; derived from the referenced manifest when omitted. |

#### Form B — inline agent definition

A full embedded `kind: Agent` manifest (same fields as a standalone `agent.yaml`) is also accepted in either list. `kind`, `metadata`, and `spec` are required; `apiVersion` is optional.

**Example:**

```yaml
agency:
  agents:
    - id: broker
      ref: ./agents/broker.yaml       # Form A
    - kind: Agent                      # Form B — inline
      metadata:
        name: summariser
      spec:
        description: "Summarises findings."
```

---

### Adding or removing MAS agents with overlays

For a MAS-targeted Overlay, `spec.patch.agents.$op` operates on
`spec.agency.agents`:

```yaml
target:
  kind: MAS
patch:
  agents:
    $op:
      remove: [schedule_agent]
      add:
        - id: generalist
          ref: ./agents/generalist.yaml
```

`add` and `replace` entries require both `id` and `ref`; `remove` takes agent
ids, and `clear: true` empties the participant list. These operations are only
valid in an Overlay patch. `agents_add` and `agents_remove` are not schema fields.

---

### Workflow

_Used by:_ `spec.workflow`

Declares the entry point and delegation graph. Embedded `MAS.spec.workflow`
supports `entry` and `nodes`; it has no `type` or `edges` field. The entry
agent's `design_pattern` controls its reasoning and delegation behavior.

| Field | Type | Description |
|-------|------|-------------|
| `entry` | `string` | ID of the entry-point agent (first to receive the user request). |
| `nodes` | `WorkflowNode[]` | Agent nodes in the workflow graph. See [`WorkflowNode`](#workflownode). |

**Example:**

```yaml
workflow:
  entry: broker
  nodes:
    - id: broker
      delegates_to: [flights, hotels]
    - id: flights
    - id: hotels
```

---

### WorkflowNode

_Used by:_ `spec.workflow.nodes[]`

| Field | Type | Required | Default | Description |
| ------- | ------ | ---------- | --------- | ------------- |
| `id` | `string` | **yes** | — | Node identifier — must match an `agency.agents[].id`. |
| `delegates_to` | `string[]` | no | `[]` | IDs of agents this node may delegate to. Drives the `delegate_to_<id>` tool set exposed to the entry agent's LLM. |
| `role` | `string` | no | — | Optional role label (informational). |
| `agent` | `string` | no | — | Agent id override (when the node id differs from the agent id). |
| `dispatch` | `string` | no | — | Dispatch mode (for example, `parallel`). |
| `config` | `object` | no | `{}` | Plugin-specific parameters (pattern-dependent keys). |
| `description` | `string` | no | `""` | Optional description for this node (informational). |

---

### Transport

_Used by:_ `spec.transport`

Controls how agents communicate within the MAS.

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `type` | `"local"` \| `"agent-remote"` \| `"agent-local"` | `"local"` | Communication type. |
| `mode` | `"local"` \| `"remote"` | `"local"` | High-level comm mode. |
| `emulation` | `boolean` | `true` | When `true`, delegation uses in-process function calls (no HTTP). |

**Example:**

```yaml
transport:
  type: local
  emulation: true
```

---

### Framework

_Used by:_ `spec.framework`

Selects which framework surface adapter wraps the native machinery skeleton. The lab infers the runner from `default_adapter` unless overridden at execution time.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_adapter` | `"native"` \| `"langgraph"` \| `"autogen"` \| `"crewai"` | `"native"` | Framework adapter id. `native` = direct OSS kernel. Other adapters delegate to registered `ctl` framework wrappers (future release). |

---

### MemoryStores

_Used by:_ `spec.memory_stores`

Named paths to shared memory store artifacts. All fields are optional strings.

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `episodic_ref` | `string` | `""` | Path to the episodic memory store artifact. |
| `semantic_ref` | `string` | `""` | Path to the semantic memory store artifact. |
| `procedural_ref` | `string` | `""` | Path to the procedural memory store artifact. |

---

### Telemetry

_Used by:_ `spec.telemetry`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | `string` | `""` | Path to the event log file (JSONL), relative to `mas.yaml`. |
**Example:**

```yaml
telemetry:
  path: ./traces/events.jsonl
```

---

## Topology, workflow, and routing

Three related ideas — often confused:

| Term | What it is | Where it lives | Example |
|------|------------|----------------|---------|
|------|------------|----------------|---------|
| **Topology** | Which agents exist and how they relate (team shape) | `spec.agency.agents`, overlay patches | design-space Exp 1.2 sweeps five overlays (`topo-linear-pipeline`, `topo-moderator-broker`, `topo-parallel`, `topo-supervised`, `topo-verifier`) |
| **Workflow** | Entry agent, nodes, allowed delegation targets, and optional dispatch | `spec.workflow` | Declares the delegation graph; does not define a `workflow.type` strategy |
| **Routing logic** | Per-message decisions inside a turn (which tool/delegate next) | LLM + delegation tools, agent prompts | Moderator reads the user message and chooses `schedule_agent` vs `itinerary_agent` |

**Workflow vs routing in a single user turn** — think of a trip-planning MAS answering one message:

- **Workflow** declares the entry agent and which delegation tools are available.
  - _LLM-directed:_ the entry agent chooses among its declared `delegates_to` peers.
  - _Deterministic linear:_ the entry agent's `design_pattern` dispatches to peers in a configured sequence.
  - _Parallel:_ a node with `dispatch: parallel` fans out to its declared peers.

- **Routing logic** is what happens _inside_ the moderator's turn when it decides the next move: "This is mostly a transport question → delegate to `schedule_agent`." Routing is **per message / per LLM step** (tool calls, delegation targets). Embedded MAS workflow declares `entry`, `nodes`, `delegates_to`, and `dispatch`; explicit sequential `edges` belong only to the standalone `Workflow` manifest below.

Overlays can change the graph, dispatch mode, or entry agent's design pattern without editing the base agent manifests.

**Topology in paper labs** — [`labs/design-space.lab/02-topologies/`](../../labs/design-space.lab/02-topologies/) varies topology only via scenario overlays. Example (`topo-moderator-broker`):

```yaml
spec:
  patch:
    workflow:
      entry: moderator
      nodes:
        - id: moderator
          agent: moderator_agent
          delegates_to: [schedule_agent, itinerary_agent, concierge_agent]
```

**Workflow execution in OSS:**

| Pattern | ctl behaviour |
| --------- | --------------- |
| Dynamic delegation | Default multi-agent: entry agent session; LLM uses delegation tools |
| `dispatch: parallel` | A node with `dispatch: parallel` (or `all`) fans out to its `delegates_to` peers in one act. Parallel tool-call batches run concurrently on the async engine path (`ainvoke` / `afeed`); the sync path still drains the same batch sequentially. |
| Explicit sequential graph | Standalone `kind: Workflow` (`workflow/v1`) declares `nodes` + `edges`; embedded MAS workflow does not support `edges` |
| Single agent | `topo-single-agent` overlay — one generalist, no inter-agent workflow |

### Concurrency model

The runtime stays **synchronous by default**. Single-agent CLI chat, unit tests, and the benchmark harness keep calling `invoke` / `feed` / `run_turn`. Concurrent fan-out (parallel tool calls, `dispatch: parallel` peers, concurrent `spawn_subagent`) uses additive async twins (`ainvoke`, `afeed`, `arun_turn`, `adelegate`, `aspawn`) on one cooperative event loop.

LLM providers must implement `achat_completion` as the async twin of `chat_completion`. Missing implementations fail at plugin load — they are not run on a worker thread, because that would reintroduce real OS-thread parallelism against lock-free run state (`SpawnLedger`, `InProcessCommBus`, `WorkingMemoryRegistry`).

There is no `WorkflowContract.register_impl()` in OSS. Topology + workflow are **declarative** in YAML; ctl composes and runs them.

**Stateful governance** — separate from topology: governance plugins track session state across turns. [`lifecycle-control.lab`](../../labs/lifecycle-control.lab/) stacks budget caps, guardrails, and HITL. See [contracts reference](../references/contracts.md#governance) and `runtime/boundary/gov/budget.py`.

---

## Standalone workflow manifest (`kind: Workflow`)

Most apps embed workflow directly under `MAS.spec.workflow`. The standalone `kind: Workflow`
manifest (`apiVersion: workflow/v1`) is for cases where the workflow document lives separately
and is referenced by multiple MAS manifests, or needs explicit routing edges with conditions.

### Top-level fields

| Field | Type | Required | Description |
| ------- | ------ | ---------- | ------------- |
| `apiVersion` | `string` | yes | Must be `workflow/v1`. |
| `kind` | `string` | yes | Must be `Workflow`. |
| `metadata.name` | `string` | no | Workflow identifier. |
| `metadata.description` | `string` | no | Human-readable description. |
| `spec` | object | yes | Workflow body. |

### `spec` fields

| Field | Type | Default | Description |
| ------- | ------ | --------- | ------------- |
| `entry` | `string` | `""` | ID of the entry agent — receives the initial user prompt. |
| `nodes` | `WorkflowNode[]` | `[]` | Agent nodes. Same shape as [`WorkflowNode`](#workflownode) but without `role`, `dispatch`, and `description`. |
| `edges` | `WorkflowEdge[]` | `[]` | Explicit routing edges — required for deterministic sequential flows. See [`WorkflowEdge`](#workflowedge). |
| `context_schema` | `object` | `{}` | Optional JSON Schema fragment describing shared context keys. |

### WorkflowEdge

_Used by:_ `spec.edges[]`

| Field | Type | Required | Default | Description |
| ------- | ------ | ---------- | --------- | ------------- |
| `from` | `string` | **yes** | — | Source node ID. |
| `to` | `string` | **yes** | — | Target node ID. |
| `condition` | `string` \| null | no | `null` | Optional routing condition (Python-like expression evaluated at runtime). |
| `label` | `string` | no | `""` | Human-readable label describing when this edge fires. |

**Example:**

```yaml
apiVersion: workflow/v1
kind: Workflow
metadata:
  name: research-flow
spec:
  entry: moderator
  nodes:
    - id: moderator
      agent: moderator
      delegates_to: [researcher]
    - id: researcher
      agent: researcher
  edges:
    - from: moderator
      to: researcher
```

Schema source: `GET /api/schemas/workflow`
Topology-switching overlays replace `spec.patch.workflow` or `spec.patch.agents`.
Scenario overlays are declared in [experiment.md](experiment.md); patch files,
target selectors, and grouped overrides are documented in [overlay.md](overlay.md).

---

## Schema source

```bash
# From installed package
python -c "from mas.lab.schemas.paths import runtime_schema_dir; print(runtime_schema_dir() / 'mas.schema.yaml')"
python -c "from mas.lab.schemas.paths import runtime_schema_dir; print(runtime_schema_dir() / 'workflow.schema.yaml')"

# From Web UI / controller (default port 8090)
curl http://localhost:8090/api/schemas/mas
curl http://localhost:8090/api/schemas/workflow
```

---

## See also

- [Agent manifest](agent.md)
- [Tutorial: creating a MAS](../tutorials/02-creating-a-mas/README.md)
- [Standalone workflow manifest](#standalone-workflow-manifest-kind-workflow)
