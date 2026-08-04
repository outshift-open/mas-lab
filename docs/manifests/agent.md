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

---

## Top-level fields

Every manifest starts with four required top-level fields.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `apiVersion` | `string` | yes | Must be `mas/v1`. |
| `kind` | `string` | yes | Must be `Agent`. |
| `metadata` | object | yes | Identity and tagging. See [`metadata` fields](#metadata-fields). |
| `spec` | object | yes | Runtime behaviour. See [`spec` fields](#spec-fields). |

Extension properties (`x-*`) are allowed at the top level and are ignored by the runtime (they carry UI metadata, canvas state, etc.).

**Minimal example:**

```yaml
apiVersion: mas/v1
kind: Agent
metadata:
  name: broker
spec:
  description: "Broker agent. Routes requests to specialists."
```

---

## `metadata` fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `string` | yes | — | Agent ID — must match the workflow node id that references this agent. |
| `description` | `string` | no | `""` | Human-readable description of this agent. |
| `version` | `string` | no | `"0.1.0"` | Semver string (`major.minor.patch`). |
| `tags` | `string[]` | no | `[]` | Free-form tags for filtering and grouping. |

Extension properties (`x-*`) are allowed and ignored by the runtime.

---

## `spec` fields

`spec.description` is the only required field.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `description` | `string` | **yes** | — | Routing-facing one-liner for delegation tools, AgentCard, and registry discovery. Written from the delegator's perspective. **Not** injected into the LLM system prompt — use `context.*` for prompt text. |
| `context` | `object` | no | — | Named chunks injected into the system prompt. Keys are author-defined (`role`, `intent`, …). See [`ContextChunk`](#contextchunk). |
| `params` | `object` | no | `{}` | Free-form string key/value params forwarded to infra middleware — not consumed by the kernel. |
| `models` | `ModelEntry[]` | no | `[]` | Preferred models for this agent. See [`ModelEntry`](#modelentry). |
| `design_pattern` | object \| null | no | `react` | Reasoning strategy. See [`DesignPattern`](#designpattern). |
| `context_manager` | object | no | `stack` | Context window management. See [`ContextManager`](#contextmanager). |
| `memory_seed` | `MemorySeedEntry[]` | no | — | Documents to pre-index into memory at startup. See [`MemorySeedEntry`](#memoryseedentry). |
| `memory` | string \| string[] \| object | no | — | Memory backend configuration. See [`MemoryConfig`](#memoryconfig). |
| `working_memory` | object | no | — | Cross-turn history persistence for delegated agents. See [`WorkingMemory`](#workingmemory). |
| `skills` | `string[]` | no | `[]` | Skills to activate. Name-only or `@library/name`. Resolution: app-local → libraries → packages. |
| `tools_ref` | `string` \| null | no | `null` | Logical tool-set name resolved by the infra `ToolRegistry` (e.g. `sre-tools`). No paths or extensions. |
| `tools` | `Tool[]` | no | `[]` | Per-agent tool declarations — three forms. Additive with `tools_ref`. See [`Tool`](#tool). |
| `behavior` | object | no | — | Runtime capability flags. See [`Behavior`](#behavior). |
| `governance` | `GovernanceBinding` | no | `{}` | Governance plugin list. See [`GovernanceBinding`](#governancebinding). |
| `llm` | `LlmBinding` | no | `{}` | Engine overrides (model, temperature, …). See [`LlmBinding`](#llmbinding). |
| `execution` | `ExecutionBinding` | no | `{}` | Execution mode (mock, cache, live, …). See [`ExecutionBinding`](#executionbinding). |
| `control` | `ControlBinding` | no | `{}` | Control-plane plugin configs. See [`ControlBinding`](#controlbinding). |
| `observability` | `ObservabilityBinding` | no | `null` | Observability sink plugin list. See [`ObservabilityBinding`](#observabilitybinding). |
| `infra_refs` | `string[]` | no | `[]` | Infra manifest references (LLM proxy, tool registry). Merged additively from overlays. |
| `infra_interceptors` | `string[]` | no | `[]` | Cross-cutting infra middleware (cache, chaos, …) outer-first. |

---

## Sub-schemas

### ContextChunk

_Used by:_ `spec.context.<key>`

Each value under `spec.context` is a named chunk injected into the system prompt under `[key]`. Two forms:

| Form | Type | Description |
|------|------|-------------|
| Inline string | `string` | Injected as literal text, unless the value resolves to an existing file path (e.g. `prompts/role.md` or `./prompts/role.md`). |
| File reference | `{ ref: string }` | Always loads the file at `ref`. Raises `ContextRefNotFoundError` at bootstrap when the path is missing. |

**Example:**

```yaml
context:
  role: |
    You are a telemetry analyst…
  intent:
    ref: "./prompts/intent.md"
```

---

### ModelEntry

_Used by:_ `spec.models[]`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `model` | `string` | **yes** | — | LiteLLM-style model string, e.g. `vertex_ai/gemini-3-pro-preview`. |
| `id` | `string` | no | `"main"` | Logical model ID within this agent. Use `main` for the primary model. |
| `temperature` | `number` [0.0–2.0] | no | `0.7` | Sampling temperature. |
| `max_tokens` | `integer` ≥ 1 | no | `2000` | Maximum output tokens. |

Do **not** put `api_base` or `api_key_env` here — those belong in the flavour/infra manifest.

**Example:**

```yaml
models:
  - model: vertex_ai/gemini-3-pro-preview
    temperature: 0.3
    max_tokens: 4096
```

---

### DesignPattern

_Used by:_ `spec.design_pattern`

Selects the agent's reasoning strategy (defaults to `react` when absent).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `string` | mutually exclusive with `ref` | Builtin shorthand: `react` \| `cot` \| `cot_native` \| `plan_execute` \| `tree_of_thoughts` \| `accumulator` and role aliases. |
| `ref` | `string` | mutually exclusive with `type` | Unified plugin locator — bare name, `./local/path`, `module://pkg.Class`, or `oci://registry/img:tag`. |
| `params` | `object` | no | Plugin-specific parameters. |
| `config` | `object` | no | Alias for `params` (overlay compatibility). |

**Example:**

```yaml
design_pattern:
  type: react

# or a custom plugin:
design_pattern:
  ref: module://my_pkg.patterns.MyCoT
  params:
    max_steps: 10
```

---

### ContextManager

_Used by:_ `spec.context_manager`

Controls context window management strategy (defaults to `stack` — unbounded history).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `string` | mutually exclusive with `ref` | Builtin: `stack` \| `sliding-window` \| `summarising` \| `full-history`. |
| `ref` | `string` | mutually exclusive with `type` | Plugin locator — same forms as `design_pattern.ref`. |
| `params` | `ContextManagerParams` | no | Strategy-specific parameters. See [`ContextManagerParams`](#contextmanagerparams). |
| `skills` | `string[]` | no | Skills auto-injected into the system prompt via `ContextFacetProvider` (context path; complements `spec.skills` which drives the `consult_skills` tool). |
| `memory` | `string[]` | no | Memory types whose content is auto-injected into the system prompt as context facets, e.g. `[semantic]`. |

**Example:**

```yaml
context_manager:
  type: sliding-window
  params:
    window_size: 20
```

---

### ContextManagerParams

_Used by:_ `spec.context_manager.params`

Constructor kwargs forwarded to the `ContextManagerPlugin`. All fields are optional.

| Field | Type | Description |
|-------|------|-------------|
| `max_turns` | `integer` ≥ 1 | Sliding-window / summarising — max prior exchange pairs. |
| `window_size` | `integer` ≥ 1 | Alias for `max_turns` (sliding-window). |
| `max_messages` | `integer` ≥ 1 | Stack CM — cap on total past messages. |
| `working_memory_messages` | `integer` ≥ 1 | Slice size for working-memory context source (default 20). |
| `token_budget` | `integer` ≥ 1 | Max estimated input tokens after assembly. |
| `max_tokens` | `integer` ≥ 1 | Alias for `token_budget`. |
| `reserve_tokens` | `integer` ≥ 0 | Tokens reserved for model completion (default 512). |
| `summary_threshold` | `integer` ≥ 1 | Summarising CM — token threshold before compression triggers. |
| `keep_turns` | `integer` ≥ 1 | Summarising CM — recent exchange pairs kept verbatim alongside the summary. |
| `working_memory_ref` | `string` | Registry ref for working-memory context source plugin. |
| `trimmer_ref` | `string` | Registry ref for token-budget trimmer plugin. |
| `token_budget_ref` | `string` | Alias for `trimmer_ref`. |

---

### MemorySeedEntry

_Used by:_ `spec.memory_seed[]`

Pre-indexes a document into the memory backend at startup. Useful for demos and tests that need pre-populated memory without a persistent store.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | `string` | **yes** | Document text to index. |
| `key` | `string` | no | Lookup key. |
| `source` | `string` | no | Source label / filename. |
| `id` | `string` | no | Explicit document ID. |
| `text` | `string` | no | Alias for `content`. |

**Example:**

```yaml
memory_seed:
  - source: "runbook.md"
    content: |
      ## Restart procedure
      1. Drain traffic…
```

---

### MemoryConfig

_Used by:_ `spec.memory`

Three forms are accepted:

| Form | Example | Description |
|------|---------|-------------|
| String shorthand | `memory: semantic` | Resolves to the corresponding plugin bundle. |
| Array shorthand | `memory: [semantic, episodic]` | Activates multiple named bundles. |
| Object form | `memory: {enabled: true, types: [...]}` | Full configuration — described below. |

**Object form fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `boolean` | `true` | Master switch — `false` loads no memory plugins. |
| `types` | `MemoryType[]` | `[]` | Ordered list of memory layers. See [`MemoryType`](#memorytype). |
| `persistence` | object | — | Session transcript persistence. See [`MemoryPersistence`](#memorypersistence). |
| `search` | object | — | Semantic retrieval configuration. See [`MemorySearch`](#memorysearch). |
| `citations` | object | — | Citation formatting for search results. See [`MemoryCitations`](#memorycitations). |
| `sync` | object | — | File-watching and re-indexing policy. See [`MemorySync`](#memorysync). |
| `overflow_retry` | object | — | Compaction retry on context overflow. See [`MemoryOverflowRetry`](#memoryoverflowretry). |
| `qmd` | object | — | QMD (Qualitative Memory Database) backend. See [`MemoryQMD`](#memoryqmd). |

#### MemoryType

_Used by:_ `spec.memory.types[]`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `string` | **yes** | — | Layer name: `session` \| `episodic` \| `semantic` \| `working` \| `procedural`. |
| `backend` | `string` | no | `"in-memory"` | Backend: `in-memory` \| `file` \| `sqlite-vec` \| `redis` \| `remote_tool`. |
| `params` | `MemoryBackendParams` | no | `{}` | Backend constructor kwargs. See [`MemoryBackendParams`](#memorybackendparams). |

#### MemoryBackendParams

_Used by:_ `spec.memory.types[].params`

| Field | Type | Description |
|-------|------|-------------|
| `path` | `string` | Filesystem path (file backend). |
| `url` | `string` | Connection URL (redis, remote_tool). |
| `collection` | `string` | Collection / table name. |
| `host` | `string` | Hostname. |
| `port` | `integer` | Port number. |
| `database` | `string` | Database name. |

#### MemoryPersistence

_Used by:_ `spec.memory.persistence`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `backend` | `string` | `"none"` | `none` \| `file` \| `sqlite` \| `redis`. |
| `path` | `string` | `""` | Base directory. Supports `{agent_id}` and `{session_id}` placeholders. Default: `$XDG_DATA_HOME/mas/agents/{agent_id}/sessions/`. |
| `auto_save` | `boolean` | `true` | Persist after each turn. |
| `auto_load` | `boolean` | `true` | Load session on bootstrap. |

#### MemorySearch

_Used by:_ `spec.memory.search`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `boolean` | `false` | Enable semantic search injection into context. |
| `max_results` | `integer` | `6` | Maximum retrieved chunks per query. |
| `min_score` | `number` | `0.35` | Minimum similarity score threshold. |
| `chunking.tokens` | `integer` | `400` | Chunk size in tokens for indexing. |
| `chunking.overlap` | `integer` | `80` | Overlap tokens between chunks. |
| `hybrid.enabled` | `boolean` | `true` | Enable hybrid search (vector + full-text). |
| `hybrid.vector_weight` | `number` | `0.7` | Vector score weight in hybrid ranking. |
| `hybrid.text_weight` | `number` | `0.3` | Full-text score weight in hybrid ranking. |
| `hybrid.mmr_enabled` | `boolean` | `false` | Max Marginal Relevance re-ranking. |
| `hybrid.mmr_lambda` | `number` | `0.7` | MMR lambda (diversity vs relevance). |
| `hybrid.temporal_decay_enabled` | `boolean` | `false` | Apply time-decay to scores. |
| `hybrid.temporal_decay_half_life_days` | `integer` | `30` | Half-life for temporal decay. |
| `cache.enabled` | `boolean` | `true` | Cache search results. |
| `cache.max_entries` | `integer` | `128` | Maximum cached search results. |

#### MemoryCitations

_Used by:_ `spec.memory.citations`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | `"auto"` \| `"on"` \| `"off"` | `"auto"` | Citation mode: `auto` (include when useful), `on` (always), `off` (strip source info). |
| `max_snippet_chars` | `integer` | `700` | Maximum characters per search result snippet. |

#### MemorySync

_Used by:_ `spec.memory.sync`

Controls when workspace memory files (`MEMORY.md`, `memory/*.md`) are re-indexed.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `on_session_start` | `boolean` | `true` | Re-index when a session begins. |
| `on_search` | `boolean` | `false` | Re-index before each search. |
| `interval_seconds` | `integer` | `300` | Periodic re-index interval in seconds (0 = disabled). |
| `delta_messages` | `integer` | `50` | Re-index after this many new messages. |
| `delta_bytes` | `integer` | `100000` | Re-index after this many bytes of new content. |
| `post_compaction_force` | `boolean` | `true` | Force re-index after compaction. |
| `file_watch.enabled` | `boolean` | `true` | Enable file change detection. |
| `file_watch.patterns` | `string[]` | `["MEMORY.md","memory/*.md"]` | Glob patterns to watch. |
| `file_watch.debounce_ms` | `integer` | `1500` | Debounce interval for file change events. |

#### MemoryOverflowRetry

_Used by:_ `spec.memory.overflow_retry`

When an LLM call fails because the context exceeds the window, automatically compact and retry.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `boolean` | `false` | Enable overflow detection and retry. |
| `max_retries` | `integer` | `2` | Maximum compaction + retry attempts. |
| `aggregate_timeout_seconds` | `number` | `60.0` | Maximum total time across all retries. |
| `budget_reduction_factor` | `number` | `0.7` | Multiply token budget by this factor on each retry. |

#### MemoryQMD

_Used by:_ `spec.memory.qmd`

Alternative search via external `qmd` binary (Qualitative Memory Database).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `boolean` | `false` | Enable QMD as a retriever backend. |
| `binary_path` | `string` | `""` | Path to `qmd` binary (auto-detected if empty). |
| `index_path` | `string` | `""` | Path to QMD index directory. |
| `search_mode` | `string` | `"search"` | QMD search mode. |
| `max_snippet_chars` | `integer` | `700` | Maximum characters per snippet. |
| `timeout_seconds` | `number` | `4.0` | Search timeout in seconds. |

---

### WorkingMemory

_Used by:_ `spec.working_memory`

Controls whether a delegated agent's committed conversation history (user/assistant turns) survives across separate delegation calls within the same `mas-ctl` session, keyed by `(session_id, agent_id)`.

Distinct from `spec.memory`: that's the `MemoryContract` retrieval-store subsystem (semantic/episodic/procedural search); this is the raw turn buffer a delegated agent falls back on.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `persistent` | `boolean` | `true` | `true`: reuse committed turn history across delegate calls within the same session. `false`: clear working memory before every delegate call — for agents that must be stateless per call (e.g. a formatter or translator). |
| `compaction` | `WorkingMemoryCompaction` | — | How much history to keep as it grows. See [`WorkingMemoryCompaction`](#workingmemorycompaction). Facade over `spec.context_manager` — set `context_manager` directly instead for lower-level control (takes precedence if both are set). |

**Context ID:** the delegating agent may pass `context_id` alongside `task` on a `delegate_to_<agent_id>` call to select an independent working-memory bucket for that peer (e.g. `"trip-paris"` vs `"trip-tokyo"` within one session). Omit it to use the session's default bucket.

#### WorkingMemoryCompaction

_Used by:_ `spec.working_memory.compaction`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `strategy` | `"keep_recent"` \| `"sliding_window"` \| `"summarize"` | `"keep_recent"` | Compaction strategy (see below). |
| `max_messages` | `integer` ≥ 1 | — | `keep_recent` — cap on total committed messages. |
| `window_size` | `integer` ≥ 1 | — | `sliding_window` — number of recent exchange pairs to keep. |
| `summary_threshold` | `integer` ≥ 1 | `4000` | `summarize` — estimated-token threshold before compaction triggers. |
| `keep_turns` | `integer` ≥ 1 | `10` | `summarize` — recent exchange pairs kept verbatim alongside the summary. |

**Strategies:**

- `keep_recent` — cap total messages at `max_messages`, no LLM call.
- `sliding_window` — keep the last `window_size` exchange pairs, no LLM call.
- `summarize` — compress older turns into one summary block via this agent's own model, keeping `keep_turns` recent pairs verbatim. Degrades to `keep_recent` when no live model is available.

**Example:**

```yaml
working_memory:
  persistent: true
  compaction:
    strategy: summarize
    summary_threshold: 4000
    keep_turns: 10
```

---

### Tool

_Used by:_ `spec.tools[]`

Three forms are accepted. All are additive with `tools_ref`.

#### Form A — manifest reference (recommended)

References a `kind: Tool` manifest file or a `ToolBundle` entry.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `ref` | `string` | **yes** | — | Path to a `kind: Tool` manifest (`./tools/calc.tool.yaml`) or a ToolBundle entry (`bundle://sre-tools/check-health`). |
| `priority` | `integer` | no | `100` | Registration priority (higher = loaded first). |

#### Form B — inline anonymous

Inline declaration for a Python class, remote tool, or OpenAPI endpoint.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `module_path` | `string` | **yes** | — | Dotted Python module path or relative file path (`./tools/my_tool.py`). |
| `kind` | `"python"` \| `"remote_tool"` \| `"openapi"` | no | `"python"` | Implementation kind. |
| `class_name` | `string` | no | — | Class name in the module. Auto-discovered when omitted. |
| `priority` | `integer` | no | `100` | Registration priority. |
| `params` | `object` | no | `{}` | Optional tool-specific init params. |

#### Form C — semantic name

A bare string resolved by the flavour's `tool_providers` (e.g. `web-search`, `calculator`, `memory-search`).

**Example:**

```yaml
tools:
  - ref: ./tools/calculator.tool.yaml          # Form A
  - module_path: library-samples/tools/calc.py  # Form B
    class_name: CalcTool
  - web-search                                  # Form C
```

---

### Behavior

_Used by:_ `spec.behavior`

Structural/semantic flags that affect which system tools and capabilities are exposed to the agent's LLM at runtime.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `share_reasoning` | `boolean` | `false` | When `true`, the `send_to_caller` tool exposes an optional `reasoning_context` parameter. The sub-agent may provide a concise summary of HOW it reached its answer (key evidence, decision points, confidence signals), forwarded to the orchestrator as `result["reasoning"]`. Enable only for trusted internal agents where context leakage is acceptable. |
| `delegation_style` | `"typed"` | `"typed"` | Controls which delegation tools are registered. `typed`: `delegate_to_<id>` tools derived from the MAS workflow. |

---

### GovernanceBinding

_Used by:_ `spec.governance`

An ordered list of governance plugin stanzas (typically applied via overlay). Each entry is either a bare plugin id string or a single-key object mapping the plugin id to its config object.

```yaml
governance:
  - policy-enforcer                        # bare id
  - rate-guard:                            # id-keyed config object
      requests_per_minute: 60
```

Plugin ids are resolved at runtime from the plugin registry. Any registered plugin (built-in or third-party) is valid without editing the schema.

---

### LlmBinding

_Used by:_ `spec.llm`

`EngineContract` / `LiveLlmEngine` overrides. These complement `spec.models[]` — prefer `models` for per-agent routing and use `llm` for env-level or overlay-level adjustments.

| Field | Type | Description |
|-------|------|-------------|
| `model` | `string` | LiteLLM-style model string override. |
| `provider` | `string` | Engine provider hint (`mock`, `openai`, `azure`, …). |
| `temperature` | `number` [0–2] | Sampling temperature override. |
| `max_tokens` | `integer` ≥ 1 | Maximum output tokens override. |

**Example:**

```yaml
llm:
  provider: mock
```

---

### ExecutionBinding

_Used by:_ `spec.execution`

Controls the engine execution mode.

| Field | Type | Description |
|-------|------|-------------|
| `mocking.enabled` | `boolean` | Enable mock engine (no real LLM calls). |
| `cache.enabled` | `boolean` | Enable response caching. |
| `live` | `boolean` | Force live engine (disable mock/cache). |
| `parallel` | `boolean` | Enable parallel tool execution. |
| `timeout` | `number` ≥ 0 | Per-call timeout in seconds. |

**Example:**

```yaml
execution:
  mocking:
    enabled: true
```

---

### ControlBinding

_Used by:_ `spec.control`

Control-plane plugin configs keyed by plugin id. Set a key to `null` to disable the plugin.

| Key | Fields | Description |
|-----|--------|-------------|
| `budget` | `max_tokens: integer`, `max_cost_usd: number` | Token or cost budget enforcement. |
| `circuit_breaker` | `failure_threshold: integer`, `reset_timeout_s: number` | Open circuit after `failure_threshold` consecutive failures; reset after `reset_timeout_s`. |
| `rate_limiter` | `requests_per_minute: integer` | Limit LLM call rate. |

**Example:**

```yaml
control:
  budget:
    max_tokens: 50000
  rate_limiter:
    requests_per_minute: 30
```

---

### ObservabilityBinding

_Used by:_ `spec.observability`

An ordered list of observability sink plugin ids. OSS sinks: `native`, `otel`.

Each entry is either a bare plugin id or a single-key config object:

```yaml
observability:
  - native                                 # bare id — defaults
  - native:                               # with config
      path: ./traces
      events_file: events.jsonl
  - otel:
      output_path: ./otel-traces
      otel_file: spans.json
```

Unknown plugin ids fail at load time. Extended sinks (`observe_sdk`, etc.) are internal-only.

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

- [MAS manifest](mas.md) — topology, transport, and delegation
- [Overlay manifest](overlay.md) — overrides
- [Tutorial: building an agent](../tutorials/01-building-an-agent/README.md)
- [Design patterns](agent.md#designpattern) — `spec.design_pattern` on agents
