# OTel Telemetry — input to the thin `norm.normalize()` wrapper
#
# OTel→KG in this library is `mas.library.kg.observability.otel_via_norm.normalize_otel`,
# which reshapes SDK JSON onto ClickHouse keys and calls `norm.normalize()`.
# Abandoned local reconstruction (`observability/otel`, `handlers`, `observe`) is not present.
# The sections below remain as a span-format reference for those wire shapes.

**Document:** `library-kg/docs/otel-telemetry.md`
**Scope:** OpenTelemetry span formats accepted by the OTel→KG path (`norm.normalize()`).

See also: [normalization.md](normalization.md) · [native-telemetry.md](native-telemetry.md)


---

## Table of Contents

1. [Overview](#1-overview)
2. [Span Naming Conventions](#2-span-naming-conventions)
3. [Format Variants](#3-format-variants)
4. [Common Attributes](#4-common-attributes)
5. [Span Reference](#5-span-reference)
   - 5.1 [Session Spans](#51-session-spans)
   - 5.2 [Agent Spans](#52-agent-spans)
   - 5.3 [LLM Spans](#53-llm-spans)
   - 5.4 [Tool Spans](#54-tool-spans)
   - 5.5 [Memory Spans](#55-memory-spans)
   - 5.6 [Workflow / MAS-Call Spans](#56-workflow--mas-call-spans)
   - 5.7 [Routing Spans](#57-routing-spans)
   - 5.8 [Processing Spans](#58-processing-spans)
   - 5.9 [Governance Spans](#59-governance-spans)
   - 5.10 [Diagnostic Spans (insightClaw only, suppressed)](#510-diagnostic-spans-insightclaw-only-suppressed)
6. [observe-sdk (ioa\_observe) — How It Works](#6-observe-sdk-ioa_observe--how-it-works)
7. [Plugin Alignment Rationale](#7-plugin-alignment-rationale)
8. [MAS Extensions (feat/mas-extensions)](#8-mas-extensions-featmas-extensions)
9. [Span Validation Schema](#9-span-validation-schema)
10. [Usage Guide](#10-usage-guide)
11. [Mapping to Native Events](#11-mapping-to-native-events)

---

## 1. Overview

The OTel normalization path accepts OpenTelemetry spans produced by three source systems and converts them into native MAS events (`events.jsonl`) before the standard normalization pipeline runs.

### OTel normalization modes

The OTel path in `library-kg` should be understood as supporting three operational modes:

1. **Extended OTel, no heuristics**
  - Input spans carry MAS-specific attributes explicitly.
  - `convert_spans_to_events(...)` should be able to map directly to native events.
  - Integration intent: `allow_heuristics=false`, `strict=true`.

2. **Standard OTel, heuristics allowed**
  - Input spans are structurally valid OTel but do not carry all MAS-specific fields.
  - Compatibility logic may synthesize or infer missing MAS events when enabled.
  - Current concrete example: `synthesize_llm_gaps=True`.

3. **Hybrid mode**
  - Use explicit attributes when present.
  - Fall back to compatibility logic only for missing information, and only when allowed by the caller.

In the current `library-kg` codebase, the built-in controls are:

| Intended integration attribute | Current `library-kg` control |
|---|---|
| `allow_heuristics` | `synthesize_llm_gaps` on the OTel conversion path, plus OTel-only compatibility recovery |
| `strict` | `strict=True` on `convert_spans_to_events(...)` and `build_kg_from_otel_spans(...)` |

This module exposes `allow_heuristics` directly on the OTel conversion path.

```
┌─────────────────────────────────┐
│  ObserveSDKPlugin               │  ioa_observe.* namespace · snake_case wire format
│  (Python / mas-lab MAS SDK)     │
└────────────────┬────────────────┘
                 │
┌────────────────┴────────────────┐
│  OtelObservabilityPlugin        │  ioa_observe.* namespace · snake_case wire format
│  (Python / MAS framework)       │
└────────────────┬────────────────┘
                 │                         ┌──────────────────────────────────────┐
┌────────────────┴────────────────┐        │  OTel Normalizer                     │
│  insightClaw TypeScript runtime │───────▶│  (otel/normalizer.py)                │──▶ events.jsonl
│  (openclaw.* namespace)         │        │  auto-detects format variant          │
└─────────────────────────────────┘        │  classifies spans by naming suffix    │
                                           │  or ioa_observe.span.kind attribute   │
                                           └──────────────────────────────────────┘
```

All three source systems target an identical logical attribute schema so a single normalizer code path handles all input. The two Python plugins emit the **ioa_observe / MAS SDK** wire format; insightClaw emits the **OpenClaw / ClickHouse** wire format. Format auto-detection occurs at the top-level key casing (see [Section 3](#3-format-variants)).

The normalizer does **not** parse MAS-Lab legacy spans (`AgentCall`, `LLMCall`, `ToolCall`) unless they carry a `mas.boundary` attribute marking them as pre-unification spans. Those spans enter a compatibility shim before the main classification logic.

### Heuristics currently used on the OTel path

The main explicit heuristic currently exposed by `library-kg` is:

- `synthesize_llm_gaps=True`: synthesize `llm_call_start/end` pairs when an agent span has no child LLM span.

Additional tolerant behavior exists around format detection and partial span acceptance, but the long-term target remains:

- native telemetry: direct normalization,
- extended OTel: direct normalization,
- standard OTel: hybrid normalization with heuristics only when allowed.

---

## 2. Span Naming Conventions

Three naming conventions co-exist in the wild. The normalizer uses suffix detection as the primary classification mechanism, falling back to the `ioa_observe.span.kind` attribute when the span name does not match a known suffix pattern.

| Convention | Origin | Pattern | Example |
|---|---|---|---|
| **ioa_observe** | ObserveSDKPlugin, OtelObservabilityPlugin | `{entity_name}.{kind}` | `research_agent.agent`, `gpt-4o.llm` |
| **insightClaw** | TypeScript runtime (openclaw.\*) | `openclaw.{domain}.{operation}` | `openclaw.llm.call`, `openclaw.agent.turn` |
| **MAS-Lab legacy** | Pre-unification spans | Bare PascalCase | `AgentCall`, `LLMCall`, `ToolCall` |

### Kind suffix vocabulary

The `{kind}` suffix in the ioa_observe convention maps directly to the span classification used downstream:

| Suffix | Span class | Notes |
|---|---|---|
| `.agent` | AgentCall | Also matched by `openclaw.agent.turn` |
| `.llm` | LLMCall | Also matched by `openclaw.llm.call`, `mas.llm.call` |
| `.tool` | ToolCall | Also matched by `tool.*` (insightClaw tool span names) |
| `.workflow` | WorkflowCall | Also matched by `openclaw.request`, `mas.agent.communication` |
| `.routing` | RoutingCall | |
| `.task` | TaskCall | Used by ObserveSDKPlugin task decorator |
| `.processing` | ProcessingCall | |
| `.governance` | GovernanceCall | |
| `session.start` | SessionStart | Exact match, no suffix |
| `session.end` | SessionEnd | Exact match, no suffix |

### insightClaw tool span names

insightClaw emits individual named spans rather than a generic `.tool` suffix. All of the following map to the `ToolCall` class:

| insightClaw span name | Description |
|---|---|
| `tool.exec` | Generic tool execution |
| `tool.read` | File / resource read |
| `tool.sessions_send` | Send message to a session |
| `tool.sessions_spawn` | Spawn a new session |
| `tool.sessions_list` | List active sessions |
| `tool.session_status` | Query session status |

### Classification priority

1. Exact match on known diagnostic span names → suppressed (class `None`)
2. Suffix match on span name (`.agent`, `.llm`, `.tool`, `.workflow`, `.routing`, `.processing`, `.governance`)
3. Exact match on insightClaw `openclaw.*` names
4. Exact match on insightClaw `tool.*` names
5. `ioa_observe.span.kind` attribute value fallback
6. MAS-Lab legacy bare names with `mas.boundary` attribute
7. Unknown → `UnknownSpanBoundaryError`

---

## 3. Format Variants

The normalizer auto-detects wire format at ingestion time by inspecting the casing of the top-level span key.

### Detection rule

```python
if "SpanName" in span:          # PascalCase top-level key
    format = "openclaw"         # OpenClaw / ClickHouse format
elif "name" in span:            # snake_case top-level key
    format = "ioa_observe"      # ioa_observe / MAS SDK format
else:
    raise FormatDetectionError(span)
```

### Format 1 — OpenClaw / ClickHouse (PascalCase)

Emitted by the insightClaw TypeScript runtime. Stored in ClickHouse before being streamed to the normalizer.

```json
{
  "SpanName": "openclaw.llm.call",
  "TraceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "SpanId": "00f067aa0ba902b7",
  "ParentSpanId": "9a3c6fd1e3e25c8a",
  "StartTime": "2026-07-07T10:00:00.000000Z",
  "EndTime":   "2026-07-07T10:00:02.341000Z",
  "StatusCode": "OK",
  "SpanAttributes": {
    "gen_ai.system": "openai",
    "gen_ai.response.model": "gpt-4o-2024-11-20",
    "gen_ai.usage.input_tokens": 1024,
    "gen_ai.usage.output_tokens": 256,
    "openclaw.llm.cost_usd": 0.00192,
    "openclaw.context.limit": 128000,
    "openclaw.context.used": 14392,
    "ioa_observe.session.id": "sess_abc123"
  }
}
```

### Format 2 — ioa_observe / MAS SDK (snake_case)

Emitted by `ObserveSDKPlugin` and `OtelObservabilityPlugin`. Exported directly via OTLP or written to a local JSONL file.

```json
{
  "name": "gpt-4o.llm",
  "context": {
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7",
    "parent_span_id": "9a3c6fd1e3e25c8a"
  },
  "start_time": "2026-07-07T10:00:00.000000Z",
  "end_time":   "2026-07-07T10:00:02.341000Z",
  "status": {"status_code": "OK"},
  "attributes": {
    "ioa_observe.span.kind": "llm",
    "ioa_observe.entity.name": "gpt-4o",
    "ioa_observe.session.id": "sess_abc123",
    "ioa_observe.llm.model": "gpt-4o-2024-11-20",
    "ioa_observe.llm.tokens.prompt": 1024,
    "ioa_observe.llm.tokens.completion": 256,
    "ioa_observe.llm.cost_usd": 0.00192,
    "gen_ai.system": "openai",
    "gen_ai.response.model": "gpt-4o-2024-11-20",
    "gen_ai.usage.input_tokens": 1024,
    "gen_ai.usage.output_tokens": 256
  }
}
```

### Normalizer field mapping

After format detection, the normalizer remaps PascalCase fields to their snake_case equivalents before attribute extraction. The canonical internal representation is always snake_case.

| OpenClaw field | ioa_observe field | Internal name |
|---|---|---|
| `SpanName` | `name` | `name` |
| `TraceId` | `context.trace_id` | `trace_id` |
| `SpanId` | `context.span_id` | `span_id` |
| `ParentSpanId` | `context.parent_span_id` | `parent_span_id` |
| `StartTime` | `start_time` | `start_time` |
| `EndTime` | `end_time` | `end_time` |
| `StatusCode` | `status.status_code` | `status_code` |
| `SpanAttributes` | `attributes` | `attributes` |

---

## 4. Common Attributes

These attributes appear on **all span types** regardless of kind. Missing values are tolerated by the normalizer (substituted with `None` or a sentinel), but `ioa_observe.session.id` or `gen_ai.conversation.id` must be present on at least one span in a trace for session linkage to succeed.

| Attribute | Type | Description | Source |
|---|---|---|---|
| `service.name` | string | OTel service name; used to identify the emitting agent/service | All |
| `ioa_observe.entity.name` | string | Logical name of the instrumented entity (agent name, model name, tool name) | ioa_observe |
| `ioa_observe.entity.path` | string | Dotted path of the entity within the agent hierarchy (e.g. `orchestrator.researcher`) | ioa_observe |
| `ioa_observe.entity.version` | string | Semantic version string of the entity | ioa_observe |
| `ioa_observe.session.id` | string | Session identifier; maps to `SessionCall.sessionId` in the KG | All |
| `gen_ai.conversation.id` | string | OTel GenAI semantic convention alias for session ID | GenAI SemConv |
| `gen_ai.agent.id` | string | Stable identifier for the agent instance | GenAI SemConv |
| `gen_ai.agent.name` | string | Human-readable agent name | GenAI SemConv |
| `gen_ai.operation.name` | string | High-level operation label (e.g. `chat`, `complete`) | GenAI SemConv |

---

## 5. Span Reference

### 5.1 Session Spans

Session spans bracket the outermost lifecycle of a single user interaction. The normalizer emits a `session_start` / `session_end` native event pair from these spans.

**Span names:** `session.start`, `session.end`  
**Source systems:** ioa_observe, insightClaw (`openclaw.session.*`)

#### Attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.session.start_time` | ISO-8601 string | optional | Wall-clock time the session was initiated; may differ from span `start_time` if the session pre-dates tracing | ioa_observe |
| `ioa_observe.session.idle_timeout_ms` | integer | optional | Configured idle timeout for the session in milliseconds | ioa_observe |
| `ioa_observe.context.repetition_score` | float [0,1] | optional | Fraction of session context that is repeated content | ioa_observe |
| `ioa_observe.context.parallelisation_score` | float [0,1] | optional | Degree of parallelism observed across the session | ioa_observe |
| `ioa_observe.context.novelty_score` | float [0,1] | optional | Fraction of session context that is novel (non-cached) content | ioa_observe |

#### KG mapping

| Span field | KG node / attribute |
|---|---|
| `ioa_observe.session.id` | `SessionCall.sessionId` |
| `start_time` | `SessionCall.startTime` |
| `end_time` | `SessionCall.endTime` |
| `ioa_observe.session.idle_timeout_ms` | `SessionCall.idleTimeoutMs` |

---

### 5.2 Agent Spans

Agent spans capture a single reasoning turn of an agent. They are the primary structural unit in the KG — every `AgentCall` node originates from one of these spans.

**Span names:**
- `{entity_name}.agent` (ioa_observe convention)
- `openclaw.agent.turn` (insightClaw)

**`ioa_observe.span.kind`:** `"agent"`

#### Core attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.span.kind` | string | required | Must be `"agent"` | ioa_observe |
| `ioa_observe.entity.input` | string | recommended | Serialised input to the agent turn (user message or upstream agent output) | ioa_observe |
| `ioa_observe.entity.output` | string | recommended | Serialised output from the agent turn | ioa_observe |
| `ioa_observe.association.properties` | JSON string | optional | Arbitrary key-value metadata associated with this agent invocation | ioa_observe |
| `ioa_observe.workflow.name` | string | optional | Name of the enclosing workflow, if any | ioa_observe |
| `ioa_observe.agent.sequence` | integer | optional | Monotonic sequence number of this agent turn within the session | ioa_observe |
| `ioa_observe.agent.previous` | string | optional | `span_id` (or entity name) of the immediately preceding agent turn | ioa_observe |

#### Fork / join attributes

These attributes are set when an agent participates in a parallel execution fork. They are consumed by the normalizer to synthesise `fork` and `join` native events, which in turn produce `AgentCall` containment edges in the KG.

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.fork.id` | string | conditional | Unique identifier for this fork group; shared across all branches | ioa_observe |
| `ioa_observe.fork.branch_index` | integer | conditional | Zero-based index of this branch within the fork group | ioa_observe |
| `ioa_observe.fork.parent_name` | string | conditional | `entity_name` of the agent that initiated the fork | ioa_observe |
| `ioa_observe.fork.parent_sequence` | integer | conditional | Sequence number of the parent agent turn at fork time | ioa_observe |
| `ioa_observe.join.fork_id` | string | conditional | `fork.id` of the fork being joined; set on the join-point span | ioa_observe |
| `ioa_observe.join.branch_count` | integer | conditional | Total number of branches that were forked; set on the join-point span | ioa_observe |

**Condition:** Fork attributes (`ioa_observe.fork.*`) must all be present together or all absent. The normalizer raises `IncompleteForKAttributeError` if only a subset is present. Join attributes are independent of fork attributes and may appear on any agent span that acts as a join point.

#### KG mapping

| Span field | KG node / attribute |
|---|---|
| `ioa_observe.entity.input` | `AgentCall.input` |
| `ioa_observe.entity.output` | `AgentCall.output` |
| `ioa_observe.agent.sequence` | `AgentCall.sequenceIndex` |
| `ioa_observe.fork.id` | fork group identifier on `contains` edges |
| `ioa_observe.workflow.name` | `WorkflowCall.workflowName` (via enclosing workflow span) |

---

### 5.3 LLM Spans

LLM spans record a single synchronous model call. The normalizer maps these to `LLMCall` nodes and synthesises token-usage `CallAnnotation` nodes from the usage attributes.

**Span names:**
- `{model_name}.llm` (ioa_observe convention; model name is the entity name, e.g. `gpt-4o.llm`)
- `openclaw.llm.call` (insightClaw)
- `mas.llm.call` (MAS-Lab legacy)

**`ioa_observe.span.kind`:** `"llm"`

#### ioa_observe LLM attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.span.kind` | string | required | Must be `"llm"` | ioa_observe |
| `ioa_observe.entity.input` | string | recommended | Full prompt sent to the model (may be truncated) | ioa_observe |
| `ioa_observe.entity.output` | string | recommended | Model completion text | ioa_observe |
| `ioa_observe.llm.model` | string | recommended | Model identifier as known to the SDK (e.g. `gpt-4o-2024-11-20`) | ioa_observe |
| `ioa_observe.llm.tokens.prompt` | integer | recommended | Prompt token count | ioa_observe |
| `ioa_observe.llm.tokens.completion` | integer | recommended | Completion token count | ioa_observe |
| `ioa_observe.llm.cost_usd` | float | optional | Estimated cost in USD for this call | ioa_observe |

#### Context window analytics attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.context.total_tokens` | integer | optional | Total tokens in the effective context window at call time | ioa_observe |
| `ioa_observe.context.segment_count` | integer | optional | Number of discrete context segments assembled for this call | ioa_observe |
| `ioa_observe.context.preparation_duration_ms` | integer | optional | Time spent assembling / compressing the context before the model call | ioa_observe |
| `ioa_observe.context.limit` | integer | optional | Maximum context window size for this model | observe-sdk ext. |
| `ioa_observe.context.used` | integer | optional | Tokens actually used in this call | observe-sdk ext. |

#### OTel GenAI semantic convention attributes

These are the canonical OTel GenAI semantic convention attributes. Both Python plugins and insightClaw emit them alongside their namespace-specific equivalents.

| Attribute | Type | Required | Description |
|---|---|---|---|
| `gen_ai.system` | string | recommended | AI provider identifier (e.g. `openai`, `anthropic`, `google_vertex_ai`) |
| `gen_ai.response.model` | string | recommended | Exact model version string returned by the provider |
| `gen_ai.usage.input_tokens` | integer | recommended | Input tokens billed by the provider |
| `gen_ai.usage.output_tokens` | integer | recommended | Output tokens billed by the provider |
| `gen_ai.usage.total_tokens` | integer | optional | Total tokens billed (input + output + any overhead) |
| `gen_ai.usage.cache_read_tokens` | integer | optional | Tokens served from the provider's prompt cache (no charge or reduced charge) |
| `gen_ai.usage.cache_write_tokens` | integer | optional | Tokens written to the provider's prompt cache |

#### insightClaw-specific LLM attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `openclaw.llm.cost_usd` | float | optional | Cost computed by insightClaw's billing module | insightClaw |
| `openclaw.context.limit` | integer | optional | Context window limit as configured in insightClaw | insightClaw |
| `openclaw.context.used` | integer | optional | Tokens used in this call, per insightClaw accounting | insightClaw |

#### Attribute precedence

When both `ioa_observe.llm.tokens.prompt` and `gen_ai.usage.input_tokens` are present, the normalizer prefers `gen_ai.usage.input_tokens` as the canonical value (it is the OTel standard). The `ioa_observe.*` variant is stored as a supplementary annotation.

#### KG mapping

| Span field | KG node / attribute |
|---|---|
| `ioa_observe.entity.input` / `gen_ai.request.*` | `LLMCall.prompt` |
| `ioa_observe.entity.output` | `LLMCall.completion` |
| `ioa_observe.llm.model` / `gen_ai.response.model` | `LLMCall.model` |
| `gen_ai.usage.input_tokens` | `LLMCall.promptTokens` |
| `gen_ai.usage.output_tokens` | `LLMCall.completionTokens` |
| `gen_ai.usage.cache_read_tokens` | `LLMCall.cacheReadTokens` |
| `gen_ai.usage.cache_write_tokens` | `LLMCall.cacheWriteTokens` |
| `ioa_observe.llm.cost_usd` | `LLMCall.costUsd` |

---

### 5.4 Tool Spans

Tool spans capture a single tool invocation — from the moment the agent dispatches the call to when the result is received. In parallel-agent topologies, tool spans may carry fork attributes identical to those on agent spans.

**Span names:**
- `{tool_name}.tool` (ioa_observe convention)
- insightClaw named spans: `tool.exec`, `tool.read`, `tool.sessions_send`, `tool.sessions_spawn`, `tool.sessions_list`, `tool.session_status`

**`ioa_observe.span.kind`:** `"tool"`

#### Attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.span.kind` | string | required | Must be `"tool"` | ioa_observe |
| `ioa_observe.entity.input` | string | recommended | Serialised tool call arguments | ioa_observe |
| `ioa_observe.entity.output` | string | recommended | Serialised tool result | ioa_observe |
| `gen_ai.tool.name` | string | recommended | Name of the tool as registered in the agent's tool registry | GenAI SemConv |
| `gen_ai.tool.call.id` | string | recommended | Unique identifier for this tool call instance (matches the LLM's tool-use block ID) | GenAI SemConv |
| `ioa_observe.fork.id` | string | conditional | Fork group ID when tool runs inside a forked branch | ioa_observe |
| `ioa_observe.fork.branch_index` | integer | conditional | Branch index within the fork group | ioa_observe |
| `ioa_observe.fork.parent_name` | string | conditional | Entity name of the forking agent | ioa_observe |
| `ioa_observe.fork.parent_sequence` | integer | conditional | Sequence number of the parent agent at fork time | ioa_observe |

#### insightClaw tool span variants

Each insightClaw tool span name maps to a specific native event sub-kind used for richer KG annotation:

| insightClaw span name | Native sub-kind | KG node |
|---|---|---|
| `tool.exec` | `tool_call` | `ToolCall` (generic) |
| `tool.read` | `tool_call` | `ToolCall` with `toolName="read"` |
| `tool.sessions_send` | `tool_call` | `ToolCall` with `toolName="sessions_send"` |
| `tool.sessions_spawn` | `tool_call` | `ToolCall` — also triggers `callsAgent` edge synthesis |
| `tool.sessions_list` | `tool_call` | `ToolCall` with `toolName="sessions_list"` |
| `tool.session_status` | `tool_call` | `ToolCall` with `toolName="session_status"` |

`tool.sessions_spawn` is special: the normalizer inspects the span's output for a session ID and synthesises a `callsAgent` edge linking the spawning agent to the spawned session.

---

### 5.5 Memory Spans

Memory spans instrument reads and writes to short-term and long-term memory stores. They share the `"tool"` span kind classification but carry additional memory-specific attributes. The normalizer maps them to `ToolCall` nodes with a `ProcessingCall` annotation node capturing the memory operation metadata.

**Span names:** `{memory_store_name}.tool` — memory spans are distinguished from generic tool spans by the presence of `ioa_observe.memory.operation`.

**`ioa_observe.span.kind`:** `"tool"`

#### Attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.memory.operation` | string | required | Memory operation type: `read`, `write`, `update`, `delete`, `search` | ioa_observe |
| `ioa_observe.memory.type` | string | optional | Memory tier: `short_term`, `long_term`, `episodic`, `semantic` | ioa_observe |
| `ioa_observe.memory.result_count` | integer | optional | Number of memory items returned by a `read` or `search` operation | ioa_observe |
| `ioa_observe.memory.failure_rate` | float [0,1] | optional | Rolling failure rate for this memory store over recent calls | ioa_observe |
| `ioa_observe.memory.fragmentation` | float [0,1] | optional | Fragmentation index of the memory store (0 = compact, 1 = fully fragmented) | ioa_observe |
| `ioa_observe.memory.read_count` | integer | optional | Cumulative read operations on this memory store in the current session | ioa_observe |
| `ioa_observe.memory.write_count` | integer | optional | Cumulative write operations on this memory store in the current session | ioa_observe |
| `openclaw.memory.is_long_term` | boolean | optional | `true` when insightClaw routes the operation to the long-term memory backend | insightClaw |
| `openclaw.memory.operation` | string | optional | insightClaw's memory operation label (may differ in granularity from `ioa_observe.memory.operation`) | insightClaw |

---

### 5.6 Workflow / MAS-Call Spans

Workflow spans capture the outermost envelope of a multi-agent workflow or a cross-agent message boundary. In single-agent topologies they are typically absent; in MAS topologies they bracket the entire sequence of agent turns that fulfill a single user intent.

**Span names:**
- `{workflow_name}.workflow` (ioa_observe convention)
- `openclaw.request` (insightClaw — top-level request envelope)
- `mas.agent.communication` (MAS-Lab legacy cross-agent message)

**`ioa_observe.span.kind`:** `"workflow"`

#### Attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.span.kind` | string | required | Must be `"workflow"` | ioa_observe |
| `ioa_observe.workflow.name` | string | required | Logical name of the workflow (e.g. `research_pipeline`, `code_review`) | ioa_observe |
| `ioa_observe.entity.input` | string | recommended | Workflow-level input (the original user request) | ioa_observe |
| `ioa_observe.entity.output` | string | recommended | Workflow-level output (the final synthesised response) | ioa_observe |

#### KG mapping

| Span field | KG node / attribute |
|---|---|
| `ioa_observe.workflow.name` | `WorkflowCall.workflowName` |
| `ioa_observe.entity.input` | `WorkflowCall.input` |
| `ioa_observe.entity.output` | `WorkflowCall.output` |
| `start_time` / `end_time` | `WorkflowCall.startTime` / `WorkflowCall.endTime` |

---

### 5.7 Routing Spans

Routing spans capture the decision logic that selects the next agent to invoke. They appear between agent turns in orchestrated MAS topologies.

**Span names:** `{source}.routing` — where `source` is the name of the orchestrating agent or router component.

**`ioa_observe.span.kind`:** `"routing"`

#### Attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.span.kind` | string | required | Must be `"routing"` | ioa_observe |
| `ioa_observe.entity.output` | string | recommended | The routing decision — name of the next agent or a structured decision object | ioa_observe |

#### Notes

Routing spans are short-lived and rarely carry input attributes (the input is the context of the preceding agent turn). The normalizer uses routing spans to synthesise `callsAgent` edges: when a routing span's `ioa_observe.entity.output` matches the `entity_name` of a subsequent agent span, an edge is emitted from the routing agent to the target agent.

---

### 5.8 Processing Spans

Processing spans instrument discrete context-transformation steps such as prompt assembly, context compression, retrieval-augmented generation (RAG) retrieval, or output post-processing.

**Span names:** `{name}.processing`

#### Attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.processing.type` | string | required | Processing step type: `prompt_assembly`, `context_compression`, `rag_retrieval`, `output_filtering`, `system_prompt_injection`, or custom | ioa_observe |
| `ioa_observe.processing.actor` | string | optional | Name of the component performing the processing | ioa_observe |
| `ioa_observe.processing.tokens` | integer | optional | Token count of the processed artefact | ioa_observe |

#### KG mapping

| Span field | KG node / attribute |
|---|---|
| `ioa_observe.processing.type` | `ProcessingCall.processingName` |
| `ioa_observe.processing.actor` | `ProcessingCall.actor` |
| `ioa_observe.processing.tokens` | annotation on `ProcessingCall` |

---

### 5.9 Governance Spans

Governance spans record policy evaluation events — typically a guardrail or safety check that occurs before or after an LLM call.

**Span names:** `{policy}.governance`

#### Attributes

| Attribute | Type | Required | Description | Source |
|---|---|---|---|---|
| `ioa_observe.governance.decision_type` | string | required | Policy outcome: `allow`, `deny`, or `warn` | ioa_observe |
| `ioa_observe.governance.policy_id` | string | required | Unique identifier for the evaluated policy | ioa_observe |

#### Notes

Governance spans that result in `deny` cause the normalizer to set `AgentCall.blocked = true` on the enclosing agent span (identified by parent span ID). `warn` outcomes produce a `CallAnnotation` node attached to the enclosing agent or LLM span.

---

### 5.10 Diagnostic Spans (insightClaw only, suppressed)

The following span names are emitted by insightClaw's internal instrumentation. They carry operational telemetry about the insightClaw runtime itself (webhook delivery, message routing, session health) rather than about the MAS workload. The normalizer classifies all of them as `None` (suppressed) and does **not** emit corresponding KG nodes.

| Span name | Description |
|---|---|
| `openclaw.model.usage` | Per-request model usage summary (superseded by `openclaw.llm.call` attributes) |
| `openclaw.webhook.processed` | Inbound webhook successfully processed by insightClaw |
| `openclaw.webhook.error` | Inbound webhook processing failed |
| `openclaw.message.processed` | Message processed by the insightClaw message bus |
| `openclaw.message.sent` | Message dispatched to a downstream recipient |
| `openclaw.session.stuck` | Session detected as stuck (no progress within timeout) |
| `openclaw.tool.loop` | Tool call loop detected (same tool called repeatedly with same arguments) |
| `openclaw.command.new` | `/new` command received, resetting session state |
| `openclaw.command.reset` | `/reset` command received |
| `openclaw.command.stop` | `/stop` command received |
| `openclaw.gateway.startup` | insightClaw gateway process started |

These spans may be useful for operational debugging but are explicitly excluded from the knowledge graph to avoid polluting the workload topology with runtime plumbing events.

---

## 6. observe-sdk (ioa_observe) — How It Works

### TracerWrapper singleton

`TracerWrapper` is the central configuration object in the observe-sdk. It is instantiated once per process and configures:

1. A `TracerProvider` backed by the configured SDK (OpenTelemetry SDK or a compatible stub)
2. One or more **span exporters**: OTLP/HTTP, OTLP/gRPC, Jaeger, Zipkin, or a local file exporter
3. A `BatchSpanProcessor` that buffers spans before export
4. Resource attributes including `service.name` and `ioa_observe.entity.name`

```python
from ioa_observe import TracerWrapper, init

init(
    app_name="research-agent",
    exporter="otlp",
    endpoint="http://collector:4317",
)
```

### Span naming

`TracerWrapper` derives span names automatically from the entity name and kind:

```
span_name = f"{entity_name}.{kind}"
# e.g. "research_agent.agent", "gpt-4o.llm", "web_search.tool"
```

The `kind` is set by the decorator or context manager used to instrument the code.

### Decorators

observe-sdk provides Python decorators that open and close spans around instrumented functions:

| Decorator | Kind suffix | Typical use |
|---|---|---|
| `@agent` | `.agent` | Agent entry-point methods |
| `@workflow` | `.workflow` | Multi-agent workflow orchestrators |
| `@task` | `.task` | Discrete task functions |
| `@tool` | `.tool` | Tool implementation functions |

### Session tracking

The SDK maintains a thread-local (or async-context-local) session context. `ioa_observe.session.id` is injected automatically on every span once a session is initialised via `TracerWrapper.set_session_id(session_id)`.

### Fork / join detection

The SDK does **not** automatically detect forks. Application code must explicitly annotate fork entry and exit points using the constants from the `feat/mas-extensions` branch (see [Section 8](#8-mas-extensions-featmas-extensions)):

```python
from ioa_observe.extensions.mas import set_fork_attributes, set_join_attributes

with tracer.start_as_current_span("worker_agent.agent") as span:
    set_fork_attributes(span, fork_id="fork_42", branch_index=2,
                        parent_name="orchestrator", parent_sequence=7)
    # ... agent logic ...
```

### Backend-agnostic design

observe-sdk is backend-agnostic: the `TracerWrapper` exporter is a runtime configuration choice, not a compile-time dependency. The same instrumented code can export to Jaeger, Grafana Tempo, Honeycomb, or a local JSONL file without code changes.

---

## 7. Plugin Alignment Rationale

Both `ObserveSDKPlugin` (wraps the observe-sdk) and `OtelObservabilityPlugin` (instruments the MAS framework directly) emit spans that conform to the same logical attribute schema. This alignment is intentional and is motivated by four reasons:

1. **Single normalizer code path.** A single `otel_normalizer.py` converts spans from both plugins to native MAS events without plugin-specific branches. Adding a third plugin requires only that it adopt the attribute schema — not changes to the normalizer.

2. **Tool ecosystem compatibility.** Grafana dashboards, the span cache, and insightClaw are all consumers of the OTel telemetry. A unified attribute namespace means dashboards and queries work across all source systems without per-source field mapping.

3. **Parity with the insightClaw TypeScript framework.** insightClaw's OpenClaw format is the reference implementation for the MAS telemetry schema. The Python plugins were designed to emit equivalent attributes (with `ioa_observe.*` as the primary namespace and `openclaw.*` aliases where needed) so that cross-runtime session stitching is possible — a single trace can span Python agents and TypeScript agents.

4. **OTel GenAI semantic conventions compliance.** Both plugins emit the `gen_ai.*` attributes alongside their own namespaces. This ensures compatibility with the broader OTel ecosystem (collectors, APM tools, auto-instrumentation libraries) that understands GenAI conventions without knowing anything about `ioa_observe.*`.

---

## 8. MAS Extensions (feat/mas-extensions)

The `feat/mas-extensions` branch of the observe-sdk adds three groups of constants that formalize the attribute schema used by the normalizer. These constants are used both by instrumentation code (to set attributes consistently) and by the normalizer (to read attributes by canonical name rather than bare strings).

### Group 1 — Agent topology constants

These constants address the fork/join coordination problem in parallel MAS topologies. They are used exclusively on agent and tool spans.

| Constant | Value | Description |
|---|---|---|
| `OBSERVE_AGENT_ID` | `"ioa_observe.agent.id"` | Stable identifier for the agent instance (distinct from `service.name`) |
| `OBSERVE_AGENT_SEQUENCE` | `"ioa_observe.agent.sequence"` | Monotonic turn counter for this agent in the current session |
| `OBSERVE_AGENT_PREVIOUS` | `"ioa_observe.agent.previous"` | Reference to the preceding agent turn |
| `OBSERVE_FORK_ID` | `"ioa_observe.fork.id"` | Shared identifier across all branches of a fork |
| `OBSERVE_FORK_BRANCH_INDEX` | `"ioa_observe.fork.branch_index"` | Zero-based branch index within the fork |
| `OBSERVE_FORK_PARENT_NAME` | `"ioa_observe.fork.parent_name"` | Entity name of the agent that initiated the fork |
| `OBSERVE_FORK_PARENT_SEQUENCE` | `"ioa_observe.fork.parent_sequence"` | Sequence number of the parent at fork time |
| `OBSERVE_JOIN_FORK_ID` | `"ioa_observe.join.fork_id"` | `fork.id` of the fork being joined; set on the join-point span |
| `OBSERVE_JOIN_BRANCH_COUNT` | `"ioa_observe.join.branch_count"` | Total branch count of the fork; set on the join-point span |

**Normalizer usage:** The normalizer reads `OBSERVE_FORK_ID` and `OBSERVE_FORK_BRANCH_INDEX` to group agent spans into fork sets, then reads `OBSERVE_JOIN_FORK_ID` to identify the join point. It synthesises `fork_start` / `fork_end` native events and emits `contains` edges from the parent agent to each branch agent.

### Group 2 — OTel GenAI semantic convention constants

These constants alias the OTel GenAI specification attribute names, preventing typos and decoupling application code from the spec version string.

| Constant | Value |
|---|---|
| `GENAI_USAGE_INPUT_TOKENS` | `"gen_ai.usage.input_tokens"` |
| `GENAI_USAGE_OUTPUT_TOKENS` | `"gen_ai.usage.output_tokens"` |
| `GENAI_USAGE_TOTAL_TOKENS` | `"gen_ai.usage.total_tokens"` |
| `GENAI_USAGE_CACHE_READ_TOKENS` | `"gen_ai.usage.cache_read_tokens"` |
| `GENAI_USAGE_CACHE_WRITE_TOKENS` | `"gen_ai.usage.cache_write_tokens"` |
| `GENAI_SYSTEM` | `"gen_ai.system"` |
| `GENAI_RESPONSE_MODEL` | `"gen_ai.response.model"` |
| `GENAI_REQUEST_MODEL` | `"gen_ai.request.model"` |
| `GENAI_AGENT_ID` | `"gen_ai.agent.id"` |
| `GENAI_AGENT_NAME` | `"gen_ai.agent.name"` |
| `GENAI_OPERATION_NAME` | `"gen_ai.operation.name"` |
| `GENAI_CONVERSATION_ID` | `"gen_ai.conversation.id"` |
| `GENAI_TOOL_NAME` | `"gen_ai.tool.name"` |
| `GENAI_TOOL_CALL_ID` | `"gen_ai.tool.call.id"` |

### Group 3 — Context window analytics constants

These constants are used by the normalizer to extract context window analytics from LLM spans and synthesise `ContextContribution` nodes.

| Constant | Value | Description |
|---|---|---|
| `OBSERVE_CONTEXT_LIMIT` | `"ioa_observe.context.limit"` | Model's maximum context window (tokens) |
| `OBSERVE_CONTEXT_USED` | `"ioa_observe.context.used"` | Tokens consumed in this call |

**Normalizer usage:** When both `OBSERVE_CONTEXT_LIMIT` and `OBSERVE_CONTEXT_USED` are present, the normalizer computes a `context_utilization` ratio (`used / limit`) and stores it as an annotation on the `LLMCall` node. Calls with utilization > 0.9 receive a `high_context_pressure` flag.

---

## 9. Span Validation Schema

The normalizer performs structural validation before classification. The following pseudo-schema documents the required and optional fields per span kind. Validation failures raise typed exceptions that the normalizer's error handler logs and optionally retries with degraded extraction.

```yaml
# span-schema.yaml  (pseudo-schema — for reference only)

$defs:
  common_required:
    - name           # OR SpanName in OpenClaw format
    - start_time     # OR StartTime
    - end_time       # OR EndTime

  common_optional:
    - context.trace_id
    - context.span_id
    - context.parent_span_id
    - status.status_code
    - attributes.service.name
    - attributes.ioa_observe.session.id
    - attributes.gen_ai.conversation.id

span_kinds:

  session:
    required: [*common_required]
    optional:
      - attributes.ioa_observe.session.start_time
      - attributes.ioa_observe.session.idle_timeout_ms
      - attributes.ioa_observe.context.repetition_score
      - attributes.ioa_observe.context.parallelisation_score
      - attributes.ioa_observe.context.novelty_score

  agent:
    required: [*common_required]
    recommended:
      - attributes.ioa_observe.entity.input
      - attributes.ioa_observe.entity.output
    optional:
      - attributes.ioa_observe.agent.sequence
      - attributes.ioa_observe.agent.previous
      - attributes.ioa_observe.fork.id        # all fork.* must be co-present
      - attributes.ioa_observe.fork.branch_index
      - attributes.ioa_observe.fork.parent_name
      - attributes.ioa_observe.fork.parent_sequence
      - attributes.ioa_observe.join.fork_id
      - attributes.ioa_observe.join.branch_count

  llm:
    required: [*common_required]
    recommended:
      - attributes.gen_ai.system
      - attributes.gen_ai.response.model
      - attributes.gen_ai.usage.input_tokens
      - attributes.gen_ai.usage.output_tokens
    optional:
      - attributes.gen_ai.usage.cache_read_tokens
      - attributes.gen_ai.usage.cache_write_tokens
      - attributes.ioa_observe.llm.cost_usd
      - attributes.ioa_observe.context.limit
      - attributes.ioa_observe.context.used
      - attributes.ioa_observe.context.total_tokens

  tool:
    required: [*common_required]
    recommended:
      - attributes.gen_ai.tool.name
      - attributes.gen_ai.tool.call.id
      - attributes.ioa_observe.entity.input
      - attributes.ioa_observe.entity.output
    optional:
      - attributes.ioa_observe.fork.*          # same co-presence rule as agent

  memory:                                      # extends tool schema
    required: [*common_required, attributes.ioa_observe.memory.operation]
    optional:
      - attributes.ioa_observe.memory.type
      - attributes.ioa_observe.memory.result_count
      - attributes.ioa_observe.memory.failure_rate
      - attributes.ioa_observe.memory.fragmentation
      - attributes.ioa_observe.memory.read_count
      - attributes.ioa_observe.memory.write_count

  workflow:
    required: [*common_required, attributes.ioa_observe.workflow.name]
    optional:
      - attributes.ioa_observe.entity.input
      - attributes.ioa_observe.entity.output

  routing:
    required: [*common_required]
    recommended:
      - attributes.ioa_observe.entity.output

  processing:
    required: [*common_required, attributes.ioa_observe.processing.type]
    optional:
      - attributes.ioa_observe.processing.actor
      - attributes.ioa_observe.processing.tokens

  governance:
    required:
      - *common_required
      - attributes.ioa_observe.governance.decision_type
      - attributes.ioa_observe.governance.policy_id
```

---

## 10. Usage Guide

### OtelObservabilityPlugin configuration

`OtelObservabilityPlugin` instruments a MAS framework agent at the framework level. It requires no changes to agent code.

```python
from mas.observability import OtelObservabilityPlugin
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

plugin = OtelObservabilityPlugin(
    service_name="my-agent",
    exporter=OTLPSpanExporter(endpoint="http://otel-collector:4317"),
    session_id_provider=lambda ctx: ctx.session_id,
)

agent = MyAgent(plugins=[plugin])
```

Key configuration options:

| Option | Type | Description |
|---|---|---|
| `service_name` | string | Sets `service.name` on all spans |
| `exporter` | SpanExporter | Any OTel-compatible span exporter |
| `session_id_provider` | callable | Returns `ioa_observe.session.id` from the agent context |
| `emit_genai_attributes` | bool | Whether to emit `gen_ai.*` attributes (default: `True`) |
| `emit_costs` | bool | Whether to compute and emit `ioa_observe.llm.cost_usd` (default: `True`) |

### ObserveSDKPlugin configuration

`ObserveSDKPlugin` wraps the observe-sdk `TracerWrapper` and integrates it with the MAS plugin lifecycle.

```python
from mas.observability import ObserveSDKPlugin
from ioa_observe import TracerWrapper

tracer = TracerWrapper(
    app_name="my-agent",
    exporter="file",
    output_path="/tmp/spans.jsonl",
)

plugin = ObserveSDKPlugin(tracer_wrapper=tracer)
agent = MyAgent(plugins=[plugin])
```

### Custom instrumentation with constants

When adding instrumentation to application code beyond what the plugins provide, use the constants from `feat/mas-extensions` to ensure attribute name correctness:

```python
from ioa_observe.extensions.mas import (
    OBSERVE_AGENT_SEQUENCE,
    OBSERVE_FORK_ID,
    OBSERVE_FORK_BRANCH_INDEX,
    OBSERVE_FORK_PARENT_NAME,
    OBSERVE_FORK_PARENT_SEQUENCE,
    GENAI_USAGE_INPUT_TOKENS,
    GENAI_USAGE_OUTPUT_TOKENS,
    OBSERVE_CONTEXT_LIMIT,
    OBSERVE_CONTEXT_USED,
)

with tracer.start_as_current_span("gpt-4o.llm") as span:
    span.set_attribute(GENAI_USAGE_INPUT_TOKENS, response.usage.input_tokens)
    span.set_attribute(GENAI_USAGE_OUTPUT_TOKENS, response.usage.output_tokens)
    span.set_attribute(OBSERVE_CONTEXT_LIMIT, 128_000)
    span.set_attribute(OBSERVE_CONTEXT_USED, response.usage.input_tokens)
```

### Fork / join instrumentation pattern

For parallel agent topologies, annotate each forked branch span and the join-point span explicitly:

```python
import uuid
from ioa_observe.extensions.mas import (
    OBSERVE_FORK_ID, OBSERVE_FORK_BRANCH_INDEX,
    OBSERVE_FORK_PARENT_NAME, OBSERVE_FORK_PARENT_SEQUENCE,
    OBSERVE_JOIN_FORK_ID, OBSERVE_JOIN_BRANCH_COUNT,
)

fork_id = str(uuid.uuid4())
branches = ["researcher", "analyst", "writer"]

# --- in orchestrator: launch branches ---
for i, branch_name in enumerate(branches):
    with tracer.start_as_current_span(f"{branch_name}.agent") as span:
        span.set_attribute(OBSERVE_FORK_ID, fork_id)
        span.set_attribute(OBSERVE_FORK_BRANCH_INDEX, i)
        span.set_attribute(OBSERVE_FORK_PARENT_NAME, "orchestrator")
        span.set_attribute(OBSERVE_FORK_PARENT_SEQUENCE, orchestrator_sequence)
        # ... branch agent logic (may run concurrently) ...

# --- in orchestrator: join point ---
with tracer.start_as_current_span("orchestrator.agent") as span:
    span.set_attribute(OBSERVE_JOIN_FORK_ID, fork_id)
    span.set_attribute(OBSERVE_JOIN_BRANCH_COUNT, len(branches))
    # ... synthesis logic ...
```

The normalizer will synthesise a `fork_start` native event before the first branch span and a `fork_end` native event after the join-point span, and will emit `contains` edges from the orchestrator's `AgentCall` to each branch `AgentCall`.

---

## 11. Mapping to Native Events

This table shows how each OTel span kind maps to the native MAS event kind consumed by the standard normalization pipeline (`normalizer.py`). Users working at the KG query layer should refer to [normalization.md](normalization.md) for the full KG node schema; this table covers only the OTel-to-native translation layer.

| OTel span kind / name | Native event kind | KG node class | Notes |
|---|---|---|---|
| `session.start` | `session_start` | `SessionCall` | |
| `session.end` | `session_end` | `SessionCall` | Closes open `SessionCall` |
| `{entity}.agent`, `openclaw.agent.turn` | `execution_start` + `execution_end` | `AgentCall` | |
| `{model}.llm`, `openclaw.llm.call`, `mas.llm.call` | `llm_call_start` + `llm_call_end` | `LLMCall` | Token usage → `CallAnnotation` |
| `{tool}.tool`, `tool.exec`, `tool.read` | `tool_call_start` + `tool_call_end` | `ToolCall` | |
| `tool.sessions_spawn` | `tool_call_start` + `tool_call_end` | `ToolCall` | Also synthesises `callsAgent` edge |
| `tool.sessions_send` | `tool_call_start` + `tool_call_end` | `ToolCall` | |
| `tool.sessions_list` | `tool_call_start` + `tool_call_end` | `ToolCall` | |
| `tool.session_status` | `tool_call_start` + `tool_call_end` | `ToolCall` | |
| Memory span (with `ioa_observe.memory.operation`) | `tool_call_start` + `tool_call_end` | `ToolCall` + `ProcessingCall` annotation | Memory metadata → annotation node |
| `{workflow}.workflow`, `openclaw.request`, `mas.agent.communication` | `workflow_start` + `workflow_end` | `WorkflowCall` | |
| `{source}.routing` | `routing` | `RoutingCall` | Synthesises `callsAgent` edges |
| `{name}.processing` | `processing_start` + `processing_end` | `ProcessingCall` | |
| `{policy}.governance` with `allow`/`warn` | `governance_allow` | `CallAnnotation` | Attached to enclosing agent or LLM span |
| `{policy}.governance` with `deny` | `governance_deny` | `CallAnnotation` | Sets `AgentCall.blocked = true` |
| Fork attributes present on agent/tool span | `fork_start` (synthesised) | — | Triggers branch containment edges |
| Join attributes present on agent span | `fork_end` (synthesised) | — | Closes fork group |
| All diagnostic spans (`openclaw.model.usage`, etc.) | suppressed | — | No KG node emitted |
| `AgentCall` + `mas.boundary` | `execution_start` + `execution_end` | `AgentCall` | Legacy compat shim |
| `LLMCall` + `mas.boundary` | `llm_call_start` + `llm_call_end` | `LLMCall` | Legacy compat shim |
| `ToolCall` + `mas.boundary` | `tool_call_start` + `tool_call_end` | `ToolCall` | Legacy compat shim |

---

*Document generated 2026-07-07. Corresponds to `otel_normalizer.py` and `ioa_observe` observe-sdk on `feat/mas-extensions`.*
