# Native Telemetry Reference — `events.jsonl`

**Document:** `mas-lab-internal/library-kg/docs/native-telemetry.md`  
**Scope:** Canonical reference for the `events.jsonl` native trace format consumed by the MAS knowledge-graph normalizer. Covers every event kind, all required and optional fields, start/end pairing rules, and worked examples.

See also: [normalization.md](normalization.md) · [steps.md](steps.md#run_verify_events) · [ontology.md](ontology.md)

---

## Table of Contents

1. [Overview](#1-overview)
2. [File Format](#2-file-format)
3. [Global Envelope (L1)](#3-global-envelope-l1)
4. [Interval Events — Start/End Pairing (L2)](#4-interval-events--startend-pairing-l2)
5. [Kind Reference — Complete Table](#5-kind-reference--complete-table)
6. [Per-Kind Payload Reference](#6-per-kind-payload-reference)
7. [Pairing Rules and Validation](#7-pairing-rules-and-validation)
8. [Session ID Convention](#8-session-id-convention)
9. [Adding New Event Kinds](#9-adding-new-event-kinds)

---

## 1. Overview

`events.jsonl` is the **native MAS trace format** — a newline-delimited JSON file where each line is one observability event emitted by the MAS runtime's `observability_plugin.py`. It is the primary input to the normalization pipeline (`run_normalize`) that converts the event stream into a typed knowledge graph (`kg.jsonld`).

The format has three validation levels, each building on the previous:

| Level | Name | Scope |
|-------|------|-------|
| **L1** | Envelope | Fields present on every emitted line (`kind`, `timestamp`, `run_id`, `agent_id`) |
| **L2** | Interval | Structural contract for `*_start`/`*_end` paired events — matching `call_id`, correct nesting |
| **L3** | Semantic | Per-kind payload — fields the normalizer reads to populate KG node attributes |

The normalizer runs in two phases:

1. **Annotation** (`normalize_events`) — O(1) per event; maps each event to an ontology class via `KIND_TO_CLASS` in `native/mappings.py`, validates envelope fields, and injects `parent_call_id` for delegated agents.
2. **Graph extraction** (`extract_graph`) — O(n log n) total; pairs `*_start`/`*_end` events into typed nodes, resolves call containment, synthesises states and transitions, and emits edges.

### Native normalization contract

For `library-kg`, the intended contract of native telemetry is:

- normalization should be as direct as possible,
- source records should already carry the structural identifiers needed by the KG path,
- compatibility heuristics should be exceptional rather than required.

Concretely, native `events.jsonl` is expected to carry explicit values for:

- `run_id`
- `agent_id`
- `call_id` on structural interval events
- `parent_call_id` when a call is nested under another call
- layer-specific payload fields such as provenance and governance details

When these fields are emitted explicitly by the runtime, `library-kg` can normalize native traces mechanically, with little or no recovery logic. Remaining compatibility passes in the current implementation exist to support older or incomplete traces and should not be treated as the target steady state.

The normalizer tolerates unknown extra fields (forward compatibility). Kinds absent from `KIND_TO_CLASS` raise `UnknownSpanBoundaryError`; kinds explicitly mapped to `None` are silently skipped.

---

## 2. File Format

`events.jsonl` is **Newline-Delimited JSON** (NDJSON):

- One JSON object per line.
- Always UTF-8 encoded; no BOM.
- No trailing commas; standard JSON only.
- Empty lines are ignored by the loader.
- Extra fields on any event are preserved and passed through to the KG node's raw attributes (forward compatibility).
- Events are expected in emission order (monotonically non-decreasing `timestamp`), but the normalizer handles out-of-order delivery gracefully for most passes (see [Section 7](#7-pairing-rules-and-validation)).

**Example — two lines from an events.jsonl:**

```json
{"kind":"execution_start","agent_id":"planner","call_id":"tp-exec-001","parent_call_id":"tp-mas-001","session_id":"trip-planner/demo/baseline/item1/r1","boundary":"AgentCall","timestamp":1716200001.0,"input":"Plan a 3-day trip to Paris."}
{"kind":"execution_end","agent_id":"planner","call_id":"tp-exec-001","parent_call_id":"tp-mas-001","session_id":"trip-planner/demo/baseline/item1/r1","status":"success","output":"Trip planned: AF101 NYC→CDG.","timestamp":1716200009.5}
```

---

## 3. Global Envelope (L1)

Every line in `events.jsonl` must carry the four **required** envelope fields. The **recommended** fields are populated by the runtime when available and improve graph quality but do not cause validation failures when absent.

### Required fields

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `string` | Event kind identifier. Must be a key in `native/mappings.py:KIND_TO_CLASS` or the normalizer raises `UnknownSpanBoundaryError`. |
| `timestamp` | `float` | Unix epoch seconds. Use a float for sub-second precision (e.g. `1716200001.235`). |
| `run_id` | `string` | Run identifier grouping all events in one trace. Typically a short slug like `r1` or a UUID. All events in a single `events.jsonl` file should share the same `run_id`. |
| `agent_id` | `string` | Identifier of the agent emitting this event. Used by containment inference and the `executedBy` edge. |

### Recommended fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `string` | Lab hierarchy path identifying the experiment run. Format: `{lab}/{experiment}/{scenario}/{item}/{run}` (see [Section 8](#8-session-id-convention)). Example: `trip-planner/demo/baseline/item1/r1`. |
| `mas_id` | `string` | Multi-agent system identifier. Used to link the trace to a named MAS topology. |
| `block` | `string` | Observability block: `structural`, `execution`, `trajectory`, or `governance`. Set automatically by the runtime; used by dashboards for visual grouping. |
| `layer` | `string` | Ontology layer: `L0`, `L1`, `L2`, `L4`, or `L5`. Mirrors the layer taxonomy in `LAYER_KINDS`. |
| `summand` | `string` | Summand within the block, for fine-grained grouping. |
| `mealy_symbol` | `string` | Mealy machine symbol label for trajectory analysis. |

---

## 4. Interval Events — Start/End Pairing (L2)

**Interval events** are event kinds whose name ends with `_start` or `_end`. They model spans of execution (a tool call, LLM call, agent turn, etc.) as a matched pair. The normalizer upserts a single KG node from both halves:

- `*_start` creates the node and sets `startTime`, envelope fields, and start-phase payload.
- `*_end` updates the same node with `endTime`, `status`, and end-phase payload.

### Pairing contract

| Rule | Detail |
|------|--------|
| **Same `call_id`** | Both events must carry the identical `call_id` UUID. This is the only join key. |
| **Same base kind** | The base (everything before `_start`/`_end`) must match. Mixed bases on the same `call_id` produce a warning from `check_interval_pairing`. |
| **Required on start** | `call_id` is required on every `*_start` event. Its absence raises `MissingCallIdError`. |
| **Recommended** | `parent_call_id` on both halves links the call to its enclosing call. |

### Resilience behaviour

| Scenario | Behaviour |
|----------|-----------|
| Start arrives before end | Normal case. Node has `startTime` set; `endTime` added when end arrives. |
| End arrives before start | Node is created from the end event (`endTime` set, `startTime=None`). Start is applied when it arrives. |
| Start with no matching end | Node is created with `endTime=None` (open call). `run_verify_events` emits a warning. |
| End with no matching start | Node is created from end only (`startTime=None`). Warning emitted. |
| Duplicate start | Second start converted to a `CallAnnotation` point node rather than overwriting the original. |
| Duplicate end | Last-writer-wins on `status`, `endTime`, and output fields. |

### Interval fields (L2)

In addition to the L1 envelope, all interval events carry:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `call_id` | `string` | Required on `*_start`; recommended on `*_end` | UUID identifying this call span. Must be unique per call within the trace. |
| `parent_call_id` | `string` | Recommended | `call_id` of the enclosing call. Absent for root calls (e.g. `mas_call_start` at the top of the tree). |

---

## 5. Kind Reference — Complete Table

All 75 non-suppressed event kinds. Kinds mapped to `None` in `KIND_TO_CLASS` are silently skipped; they are listed in the Suppressed section.

### 5.1 Core Execution (start/end pairs)

| Kind | KG Class | L2 Pair | Required Fields | Recommended Fields | Notes |
|------|---------|---------|----------------|--------------------|-------|
| `execution_start` | `AgentCall` or `TaskCall` | start | `call_id`, `input` | `parent_call_id`, `context`, `boundary`, `agent_type`, `agent_sequence` | Becomes `TaskCall` when `boundary=TaskCall` |
| `execution_end` | `AgentCall` or `TaskCall` | end | `status` | `output`, `parent_call_id` | `output`/`payload` → `outputContent` |
| `llm_call_start` | `LLMCall` | start | `call_id`, `model` | `parent_call_id`, `messages`, `temperature`, `max_tokens` | `messages`/`input`/`prompt` all accepted |
| `llm_call_end` | `LLMCall` | end | — | `parent_call_id`, `latency_ms`, `response`, `finish_reason`, `tokens_used` | `response.usage` → token counts |
| `tool_call_start` | `ToolCall` | start | `call_id`, `tool_name` | `parent_call_id`, `arguments`, `tool_call_id` | `arguments`/`parameters`/`tool_arguments` all accepted |
| `tool_call_end` | `ToolCall` | end | `tool_name` | `parent_call_id`, `latency_ms`, `result`, `status` | `result`/`output` → `toolOutput` |
| `mas_call_start` | `MASCall` | start | `call_id` | `parent_call_id`, `mas_id`, `session_id` | Top of the call tree |
| `mas_call_end` | `MASCall` | end | — | `parent_call_id`, `status`, `output` | |
| `rag_query_start` | `RAGQuery` | start | `call_id` | `parent_call_id`, `query_text`, `collection` | |
| `rag_query_end` | `RAGQuery` | end | — | `parent_call_id`, `status`, `retrieved_doc_count`, `results` | |
| `memory_call_start` | `MemoryCall` | start | `call_id` | `parent_call_id` | Generic memory operation |
| `memory_call_end` | `MemoryCall` | end | — | `parent_call_id`, `status` | |
| `memory_store_start` | `MemoryCall` | start | `call_id` | `parent_call_id` | Write variant |
| `memory_store_end` | `MemoryCall` | end | — | `parent_call_id`, `status` | |
| `memory_retrieve_start` | `MemoryCall` | start | `call_id` | `parent_call_id` | Read variant |
| `memory_retrieve_end` | `MemoryCall` | end | — | `parent_call_id`, `status` | |
| `processing_call_start` | `ProcessingCall` | start | `call_id` | `parent_call_id`, `processing_name`, `processing_type`, `input` | Context processing, compression, chunking |
| `processing_call_end` | `ProcessingCall` | end | — | `parent_call_id`, `status`, `output`, `tokens_input`, `tokens_output`, `compression_ratio` | `_fix_context_assembly_outputs` may backfill `processingOutput` |
| `workflow_transition_start` | `ProcessingCall` | start | `call_id` | `parent_call_id`, `processing_name` | Internal control-flow; no dedicated ontology class |
| `workflow_transition_end` | `ProcessingCall` | end | — | `parent_call_id`, `status` | |
| `skill_execution_start` | `SkillCall` | start | `call_id` | `parent_call_id`, `skill_name`, `skill_version`, `input` | |
| `skill_execution_end` | `SkillCall` | end | — | `parent_call_id`, `status`, `output` | `output` → `skillOutput` |
| `network_call_start` | `ToolCall` | start | `call_id`, `tool_name` | `parent_call_id`, `arguments` | HTTP/network call; treated identically to `tool_call_start` |
| `network_call_end` | `ToolCall` | end | — | `parent_call_id`, `status`, `output` | |

### 5.2 Core Annotation (point events)

Annotation events carry no `call_id` and are not tree nodes. They become `CallAnnotation` nodes attached to their tightest enclosing structural call via an `annotates` edge.

| Kind | KG Class | L2 Pair | Recommended Fields | Notes |
|------|---------|---------|-------------------|-------|
| `routing` | `CallAnnotation` | point | `source_agent_id`, `target_agent_id`, `task`, `correlation_id` | Also feeds `_enrich_parent_call_ids` for delegation |
| `routing_result` | `CallAnnotation` | point | `source_agent_id`, `target_agent_id`, `status`, `correlation_id` | Confirmation of routing |
| `context_assembled` | `CallAnnotation` | point | `segments`, `total_tokens` | Signals completion of context assembly |
| `state_update_start` | `CallAnnotation` | point (paired) | `operation`, `target` | Both halves produce independent annotations |
| `state_update_end` | `CallAnnotation` | point (paired) | `status` | |
| `agent_communication_start` | `CallAnnotation` | point (paired) | `source_agent_id`, `target_agent_id`, `message_type` | |
| `agent_communication_end` | `CallAnnotation` | point (paired) | `status` | |
| `checkpoint_start` | `CallAnnotation` | point (paired) | — | `block="governance"` set on the node |
| `checkpoint_end` | `CallAnnotation` | point (paired) | `status` | |
| `user_input` | `CallAnnotation` | point | `content` | UI-layer event; user message entering the system |
| `user_output` | `CallAnnotation` | point | `content` | UI-layer event; agent response to user |
| `tool_result_injected` | `CallAnnotation` | point | `tool_name` | Context provenance for tool result re-injection |

### 5.3 L2 Trajectory

Trajectory events model concurrent and branching execution topology. Included when `include_trajectory=True` (the default).

| Kind | KG Class | L2 Pair | Required Fields | Recommended Fields | Notes |
|------|---------|---------|----------------|--------------------|-------|
| `parallel_group_start` | `ParallelGroup` | start | `call_id`, `group_id` | `parent_call_id`, `branch_count`, `branches` | `branches` is a list of branch name strings |
| `parallel_group_end` | `ParallelGroup` | end | `call_id` | `parent_call_id`, `status`, `group_id` | |
| `branch_start` | `Branch` | start | `call_id` | `parent_call_id`, `branch_name` | Child of a `ParallelGroup` |
| `branch_end` | `Branch` | end | `call_id` | `parent_call_id`, `status` | |

> Note: `routing` and `routing_result` also belong to the trajectory layer (see `LAYER_KINDS["trajectory"]` in `native/mappings.py`) and are suppressed when `include_trajectory=False`.

### 5.4 L4 Provenance

Provenance events record per-part context window contributions. Included when `include_provenance=True` (off by default).

| Kind | KG Class | L2 Pair | Recommended Fields | Notes |
|------|---------|---------|-------------------|-------|
| `context_part_contributed` | `ContextContribution` | point | `part_id`, `parents`, `source`, `section_id`, `source_type`, `access_mechanism`, `cause`, `cause_type`, `token_estimate`, `retained`, `eviction_reason`, `sensitivity`, `content`, `content_preview`, `llm_call_id` | `llm_call_id` enables a direct `contributesTo` edge bypassing timestamp fallback |

### 5.5 L1 Infrastructure

Infrastructure events record worker/endpoint presence. Included when `include_infrastructure=True` (off by default).

| Kind | KG Class | L2 Pair | Recommended Fields | Notes |
|------|---------|---------|-------------------|-------|
| `infrastructure_info` | `Worker` | point | `worker_id`, `worker_pid`, `endpoint`, `durable_backend` | One node per unique `worker_id` |

### 5.6 L5 Governance

All governance events become `CallAnnotation` nodes with `block="governance"` until a dedicated `GovernanceEvent` ontology class exists. Included when `include_governance=True` (off by default).

| Kind | KG Class | Recommended Fields | Notes |
|------|---------|-------------------|-------|
| `governance_checked` | `CallAnnotation` | `hook`, `plugin`, `contract_id`, `reason`, `details` | Most common governance event |
| `governance_denied` | `CallAnnotation` | `policy_id`, `decision`, `reason`, `denied_call_id` | `deniedCallId` in KG |
| `audit` | `CallAnnotation` | `policy_id`, `decision`, `reason` | |
| `policy_denial` | `CallAnnotation` | `policy_id`, `reason`, `denied_call_id` | |
| `policy_allow` | `CallAnnotation` | `policy_id`, `reason` | |
| `budget_event` | `CallAnnotation` | `budget_scope`, `amount` | `budgetScope`, `amount` in KG |
| `transformation_event` | `CallAnnotation` | `reason` | |
| `control_intervention` | `CallAnnotation` | `intervention_type` | `interventionType` in KG |
| `hitl_gate` | `CallAnnotation` | `reason`, `decision` | Human-in-the-loop gate |
| `obs_wrap_gov_authorize_start` | `CallAnnotation` | — | Runtime wrapper |
| `obs_wrap_gov_authorize_end` | `CallAnnotation` | — | Runtime wrapper |
| `obs_wrap_gov_validate_start` | `CallAnnotation` | — | Runtime wrapper |
| `obs_wrap_gov_validate_end` | `CallAnnotation` | — | Runtime wrapper |
| `governance_authorize_start` | `CallAnnotation` | — | |
| `governance_authorize_end` | `CallAnnotation` | — | |
| `governance_validate_start` | `CallAnnotation` | — | |
| `governance_validate_end` | `CallAnnotation` | — | |

### 5.7 Legacy / Suppressed

These kinds are mapped to `None` in `KIND_TO_CLASS` and are silently skipped at normalization time. No error or warning is raised. They existed in older trace versions (pre `observability_plugin.py` v2).

| Kind | Reason Suppressed |
|------|------------------|
| `prompt_build_start` | Redundant with `llm_call_start.messages` |
| `prompt_build_end` | Redundant with `llm_call_start.messages` |
| `user_response` | Redundant with `execution_end.output` |
| `human_interaction` | Legacy UI event; no normalizer mapping |
| `delegated_agent_output` | Superseded by `execution_end` on the delegate |
| `skills_check` | Governance extension only (legacy) |
| `object_upsert` | Domain-KG extension only |
| `object_link` | Domain-KG extension only |
| `object_model_event` | Domain-KG extension only |
| `user_input_request` | Not a call node; no graph representation |

---

## 6. Per-Kind Payload Reference

All examples use the trip-planner scenario: `session_id = trip-planner/demo/baseline/item1/r1`, agents `mas`, `planner`, `itinerary_agent`.

---

### 6.1 `execution_start`

Marks the beginning of an agent's execution turn. The normalizer reads this event to create an `AgentCall` (or `TaskCall` when `boundary=TaskCall`) node.

**Normalizer reads:**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `agent_id` | `agentId` | Also used for `executedBy` edge |
| `input` / `payload` | `inputContent` | Accepts either field name |
| `boundary` | Determines node type | `"TaskCall"` → `TaskCall`; anything else → `AgentCall` |
| `agent_type` | `agentType` | Optional agent classification |
| `agent_sequence` | `agentSequence` | Ordinal position in multi-agent sequence |
| `task_name` / `task_type` | `taskName` / `taskType` | For `TaskCall` nodes only |
| `context` | `context` | Recommended; agent context at invocation time |

**Example:**

```json
{
  "kind": "execution_start",
  "agent_id": "planner",
  "call_id": "tp-exec-001",
  "parent_call_id": "tp-mas-001",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "boundary": "AgentCall",
  "timestamp": 1716200001.0,
  "input": "Plan a 3-day trip to Paris with flight booking and hotel."
}
```

---

### 6.2 `execution_end`

Closes an agent's execution turn. The normalizer updates the existing `AgentCall`/`TaskCall` node created by the matching `execution_start`.

**Normalizer reads:**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `status` | `status` | Required: `success`, `error`, `cancelled` |
| `output` / `payload` | `outputContent` | Accepts either field name |

**Example:**

```json
{
  "kind": "execution_end",
  "agent_id": "planner",
  "call_id": "tp-exec-001",
  "parent_call_id": "tp-mas-001",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "status": "success",
  "output": "Trip planned: AF101 NYC→CDG, 3 nights at Hôtel du Marais.",
  "timestamp": 1716200009.5
}
```

---

### 6.3 `llm_call_start`

Marks the beginning of a call to a language model.

**Normalizer reads:**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `model` | `modelName` | Required; e.g. `"vertex_ai/gemini-2.5-flash"` |
| `llm_name` / `agent_id` | `llmName` | Friendly display name for the LLM |
| `messages` / `input` / `prompt` | `prompt` | Formatted via `_format_messages`; all three accepted |
| `temperature` | `temperature` | Sampling temperature |
| `max_tokens` | `maxTokens` | Token budget |

**Example:**

```json
{
  "kind": "llm_call_start",
  "agent_id": "planner",
  "call_id": "tp-llm-001",
  "parent_call_id": "tp-exec-001",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "model": "vertex_ai/gemini-2.5-flash",
  "timestamp": 1716200002.0,
  "messages": [
    {"role": "system", "content": "You are a travel planning agent."},
    {"role": "user", "content": "Plan a 3-day trip to Paris."}
  ],
  "temperature": 0.7,
  "max_tokens": 1024
}
```

---

### 6.4 `llm_call_end`

Closes an LLM call and records token usage and response content.

**Normalizer reads:**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `response.usage.prompt_tokens` / `input_tokens` | `promptTokenCount` | Either nested path accepted |
| `response.usage.completion_tokens` / `output_tokens` | `completionTokenCount` | |
| `response.usage.total_tokens` | `totalTokenCount` | |
| `response.model` | `modelName` | Actual model used (may differ from requested) |
| `response.id` | `responseId` | Provider response ID |
| `response.choices[0].finish_reason` | `finishReason` | `stop`, `length`, `tool_calls`, etc. |
| `response.thinking` | `thinking` | Extended thinking output (Anthropic) |
| `latency_ms` | `latencyMs` | End-to-end call duration |

**Example:**

```json
{
  "kind": "llm_call_end",
  "agent_id": "planner",
  "call_id": "tp-llm-001",
  "parent_call_id": "tp-exec-001",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "status": "success",
  "timestamp": 1716200003.5,
  "latency_ms": 1500,
  "response": {
    "id": "resp-abc123",
    "model": "gemini-2.5-flash",
    "choices": [
      {
        "message": {"role": "assistant", "content": "Delegating to itinerary_agent."},
        "finish_reason": "stop"
      }
    ],
    "usage": {
      "prompt_tokens": 80,
      "completion_tokens": 18,
      "total_tokens": 98
    }
  }
}
```

---

### 6.5 `tool_call_start`

Marks the beginning of a tool invocation.

**Normalizer reads:**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `tool_name` | `toolName` | Required |
| `tool_call_id` | `toolCallId` | Provider-assigned tool call ID (e.g. from OpenAI function calling) |
| `arguments` / `tool_arguments` / `parameters` | `toolArguments` | JSON-encoded; all three accepted |

**Example:**

```json
{
  "kind": "tool_call_start",
  "agent_id": "itinerary_agent",
  "call_id": "tp-tc-001",
  "parent_call_id": "tp-pg-001",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "tool_name": "search_flights",
  "timestamp": 1716200005.1,
  "arguments": {
    "origin": "NYC",
    "destination": "CDG",
    "date": "2026-07-01"
  }
}
```

---

### 6.6 `tool_call_end`

Closes a tool call and records the result.

**Normalizer reads:**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `tool_name` | `toolName` | Required on end (for verification) |
| `output` / `result` | `toolOutput` | Either field accepted |
| `status` | `status` | `success` or `error` |
| `latency_ms` | `latencyMs` | |

**Example:**

```json
{
  "kind": "tool_call_end",
  "agent_id": "itinerary_agent",
  "call_id": "tp-tc-001",
  "parent_call_id": "tp-pg-001",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "status": "success",
  "tool_name": "search_flights",
  "timestamp": 1716200006.5,
  "result": {
    "flights": [{"id": "AF101", "dep": "08:00", "arr": "21:30", "price_usd": 680}]
  }
}
```

---

### 6.7 `mas_call_start` / `mas_call_end`

Brackets the entire multi-agent system invocation. Typically the root of the call tree.

**Normalizer reads:**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `mas_id` | `masId` | MAS system identifier |
| `session_id` | `sessionId` | Propagated to the `Session` node |

**Examples:**

```json
{"kind":"mas_call_start","agent_id":"mas","call_id":"tp-mas-001","session_id":"trip-planner/demo/baseline/item1/r1","run_id":"r1","timestamp":1716200000.0}

{"kind":"mas_call_end","agent_id":"mas","call_id":"tp-mas-001","session_id":"trip-planner/demo/baseline/item1/r1","run_id":"r1","status":"success","timestamp":1716200010.0,"output":"3-day Paris trip: AF101 NYC→CDG on 2026-07-01, Hôtel du Marais (€195/night)."}
```

---

### 6.8 `rag_query_start` / `rag_query_end`

Brackets a retrieval-augmented generation query.

**Recommended fields:**

| Field | Direction | Description |
|-------|-----------|-------------|
| `query_text` | start | The natural-language query string |
| `collection` | start | Vector store collection or index name |
| `retrieved_doc_count` | end | Number of documents retrieved |
| `results` | end | List of retrieved document objects |
| `status` | end | `success` or `error` |

**Examples:**

```json
{"kind":"rag_query_start","agent_id":"itinerary_agent","call_id":"tp-rag-001","parent_call_id":"tp-pg-001","run_id":"r1","session_id":"trip-planner/demo/baseline/item1/r1","query_text":"Paris boutique hotels near Marais district budget 200 EUR/night","collection":"hotels-europe","timestamp":1716200005.2}

{"kind":"rag_query_end","agent_id":"itinerary_agent","call_id":"tp-rag-001","parent_call_id":"tp-pg-001","run_id":"r1","session_id":"trip-planner/demo/baseline/item1/r1","status":"success","retrieved_doc_count":4,"results":[{"name":"Hôtel du Marais","price_eur":195,"rating":4.6}],"timestamp":1716200006.8}
```

---

### 6.9 `routing`

A point event (no `call_id`) signalling that an agent is delegating to another agent. The normalizer uses this event in two ways:

1. Creates a `CallAnnotation` node attached to the current agent's enclosing call.
2. In `_enrich_parent_call_ids`, injects `parent_call_id` into the target agent's subsequent `execution_start` if that event arrives without one.

**Normalizer reads:**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `source_agent_id` | `sourceAgentId` | Delegating agent |
| `target_agent_id` | `targetAgentId` | Receiving agent |
| `task` | `task` | Task description being delegated |
| `correlation_id` | `correlationId` | Ties routing to routing_result |

**Example:**

```json
{
  "kind": "routing",
  "agent_id": "planner",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "source_agent_id": "planner",
  "target_agent_id": "itinerary_agent",
  "task": "Build a 3-day Paris itinerary with flights and hotels.",
  "correlation_id": "corr-001",
  "timestamp": 1716200003.9
}
```

---

### 6.10 `context_assembled`

A point event signalling that the context window has been fully assembled before an LLM call. Annotates the enclosing `LLMCall` node.

**Recommended fields:**

| Field | Description |
|-------|-------------|
| `segments` | List of context segment descriptors |
| `total_tokens` | Total token count of the assembled context |

**Example:**

```json
{
  "kind": "context_assembled",
  "agent_id": "planner",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "total_tokens": 512,
  "segments": ["system_prompt", "conversation_history", "tool_results"],
  "timestamp": 1716200001.9
}
```

---

### 6.11 `context_part_contributed`

A point event recording the contribution of a single part to the context window. Used to build the provenance graph (L4). Requires `include_provenance=True` to reach the KG.

**Normalizer reads:**

| Event field | KG attribute / edge | Notes |
|-------------|---------------------|-------|
| `part_id` | `partId` | Stable ID for this contribution |
| `parents` | `derivedFrom` edges | List of parent `part_id` values |
| `source` | `source` | Origin of the content (e.g. `"tool_result"`, `"memory"`) |
| `section_id` | `sectionId` | Context section this part belongs to |
| `source_type` | `sourceType` | Taxonomy of source |
| `access_mechanism` | `accessMechanism` | How the content was retrieved |
| `cause` | `cause` | What caused this contribution |
| `cause_type` | `causeType` | Taxonomy of cause |
| `token_estimate` | `tokenEstimate` | Estimated token count for this part |
| `retained` | `retained` | `true` if the part is in the final context window |
| `eviction_reason` | `evictionReason` | Present when `retained=false` |
| `sensitivity` | `sensitivity` | Data sensitivity classification |
| `content` / `content_preview` | `content` | Full content or preview |
| `llm_call_id` | `contributesTo` edge | Direct link to the LLM call; faster than timestamp fallback |

**Example:**

```json
{
  "kind": "context_part_contributed",
  "agent_id": "itinerary_agent",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "part_id": "part-hotel-rag-001",
  "source": "rag_result",
  "section_id": "retrieved_context",
  "access_mechanism": "vector_search",
  "cause": "user_query",
  "cause_type": "direct",
  "token_estimate": 142,
  "retained": true,
  "sensitivity": "public",
  "content_preview": "Hôtel du Marais: €195/night, rating 4.6, near Place des Vosges.",
  "llm_call_id": "tp-llm-002",
  "parents": [],
  "timestamp": 1716200007.1
}
```

---

### 6.12 `parallel_group_start` / `parallel_group_end`

Brackets a group of concurrently executing branches.

**Normalizer reads:**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `group_id` | `groupId` | Must match on start and end |
| `branch_count` | `branchCount` | Expected number of concurrent branches |
| `branches` | `branches` | List of branch name strings |

**Examples:**

```json
{"kind":"parallel_group_start","agent_id":"itinerary_agent","call_id":"tp-pg-001","parent_call_id":"tp-exec-002","run_id":"r1","session_id":"trip-planner/demo/baseline/item1/r1","group_id":"tp-pg-001","branch_count":2,"branches":["flights","hotels"],"timestamp":1716200005.0}

{"kind":"parallel_group_end","agent_id":"itinerary_agent","call_id":"tp-pg-001","parent_call_id":"tp-exec-002","run_id":"r1","session_id":"trip-planner/demo/baseline/item1/r1","group_id":"tp-pg-001","status":"success","timestamp":1716200007.0}
```

---

### 6.13 `governance_checked`

The most common governance event. A point event recording that a governance policy was evaluated. Becomes a `CallAnnotation` with `block="governance"`.

**Normalizer reads (via `_ANN_KEY_MAP`):**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `policy_id` | `policyId` | Policy that was checked |
| `decision` | `decision` | `allow` or `deny` |
| `reason` | `reason` | Human-readable reason |
| `denied_call_id` | `deniedCallId` | Present when `decision=deny` |

**Example:**

```json
{
  "kind": "governance_checked",
  "agent_id": "planner",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "hook": "pre_agent_communication",
  "plugin": "RoutingPlugin",
  "contract_id": "routing",
  "reason": "planner → itinerary_agent: found in declared edges",
  "details": {"source_id": "planner", "target_id": "itinerary_agent"},
  "timestamp": 1716200003.8
}
```

---

### 6.14 `infrastructure_info`

Records worker/endpoint presence at the start of a run. Becomes a `Worker` node. Requires `include_infrastructure=True`.

**Normalizer reads:**

| Event field | KG attribute | Notes |
|-------------|-------------|-------|
| `worker_id` | `workerId` | Unique worker identifier |
| `worker_pid` | `workerPid` | OS process ID |
| `endpoint` | `endpoint` | Service endpoint URL or address |
| `durable_backend` | `durableBackend` | Durable state backend type |

**Example:**

```json
{
  "kind": "infrastructure_info",
  "agent_id": "mas",
  "run_id": "r1",
  "session_id": "trip-planner/demo/baseline/item1/r1",
  "worker_id": "worker-001",
  "worker_pid": 42817,
  "endpoint": "http://localhost:8080",
  "durable_backend": "redis",
  "timestamp": 1716199999.0
}
```

---

## 7. Pairing Rules and Validation

The `run_verify_events` step (module `mas.library.kg.steps.verify_events`) runs structural validation on a raw `events.jsonl` before normalization. It calls `check_interval_pairing` from `native/validate.py`.

### Invariants checked

| Invariant | Severity | Description |
|-----------|----------|-------------|
| **Every `*_start` has a matching `*_end`** | Warning | Identified by `call_id`. A start with no matching end produces an open call node (`endTime=None`) in the KG — valid but typically indicates a crashed or incomplete trace. |
| **Every `*_end` has a matching `*_start`** | Warning | An end with no matching start produces a node with `startTime=None`. Indicates out-of-order or partial trace. |
| **`call_id` required on `*_start`** | Error | Absence raises `MissingCallIdError` during normalization. |
| **No mixed interval bases on the same `call_id`** | Warning | If `call_id X` has both `tool_call_start` and `llm_call_start` events, `check_interval_pairing` warns `"mixed interval bases"`. |
| **`start_time ≤ end_time`** | Warning | Emitted by the KG structural verifier (`core/verifier.py`) after normalization. |
| **Unique `call_id` per open call** | Structural | A second `*_start` before the matching `*_end` is treated as a duplicate: converted to a `CallAnnotation` point node rather than overwriting the original. |
| **Child `parent_call_id` = parent `call_id`** | Structural | Enforced by `_infer_contains_edges`. Mismatched links produce disconnected subtrees (logged at DEBUG). |

### Running validation

```python
from mas.library.kg.steps import run_verify_events

# Default: required-field strictness, raises on hard errors
report = run_verify_events("events.jsonl")

# Lenient: collect all warnings without raising
report = run_verify_events("events.jsonl", strictness="required", fail_on_error=False)

print(report["ok"])           # True / False
print(report["pairing"])      # {"ok": True/False, "warnings": [...]}
print(report["error_count"])  # int
```

Report keys:

| Key | Type | Description |
|-----|------|-------------|
| `ok` | `bool` | `True` if no validation errors |
| `schema_file` | `str` | Path to JSON Schema used |
| `total_events` | `int` | Total event count in the file |
| `error_count` | `int` | Number of schema errors |
| `event_errors` | `list` | First 20 per-line error details |
| `pairing` | `dict` | `{"ok": bool, "warnings": [str, ...]}` from `check_interval_pairing` |

### Example pairing warnings

```
call_id tp-tc-001: start without matching end
call_id tp-llm-999: end without matching start
call_id tp-tc-007: mixed interval bases ['llm_call', 'tool_call']
```

---

## 8. Session ID Convention

The `session_id` field encodes the lab experiment hierarchy in a single path string:

```
{lab}/{experiment}/{scenario}/{item}/{run}
```

| Segment | Description | Example |
|---------|-------------|---------|
| `lab` | Lab identifier (maps to a `lab-config.yaml`) | `trip-planner` |
| `experiment` | Experiment name within the lab | `demo` |
| `scenario` | Scenario variant | `baseline` |
| `item` | Dataset item being evaluated | `item1` |
| `run` | Run index within the item | `r1` |

**Full example:** `trip-planner/demo/baseline/item1/r1`

### Auto-derivation from `lab-config.yaml`

When `events.jsonl` sits under a directory containing a `lab-config.yaml`, the normalizer (via `run_normalize`) derives `session_id` automatically from the lab directory structure. You do not need to set it on each event.

### Manual override

Pass `--session-id` on the CLI or `session_id_override` in the Python API to override:

```bash
mas-lab graph normalize events.jsonl \
  --output kg.jsonld \
  --session-id trip-planner/demo/baseline/item1/r1
```

```python
from mas.library.kg.steps import run_normalize

artifact = run_normalize(
    "events.jsonl",
    run_id="r1",
    session_id_override="trip-planner/demo/baseline/item1/r1",
)
```

### Relationship to `run_id`

`run_id` is the leaf identifier (typically equal to the `run` segment, e.g. `r1`) and is written into every KG node. `session_id` is the full path and is written into the `Session` node and `kg.jsonld` metadata. Both are required for the normalizer to build correct `Session → Run → Agent` hierarchy nodes.

---

## 9. Adding New Event Kinds

The single authoritative location for event kind registration is:

```
src/mas/library/kg/core/event_mappings.py
```

### To add a new kind

1. Add an entry to `KIND_TO_CLASS`:

   ```python
   "my_new_event_start": "ToolCall",   # maps to an existing ontology class
   "my_new_event_end":   "ToolCall",
   ```

   The value must be the **local name of an OWL class** in `mas-ontology.ttl` (e.g. `ToolCall`, `LLMCall`, `AgentCall`, `CallAnnotation`, `ContextContribution`, `Worker`). Unknown class names are validated at normalizer startup against the ontology index.

2. If the new kind belongs to an optional layer (infrastructure, provenance, trajectory, governance), add it to `LAYER_KINDS`:

   ```python
   LAYER_KINDS: Dict[str, FrozenSet[str]] = {
       "governance": frozenset({
           ...,
           "my_new_event_start",
           "my_new_event_end",
       }),
   }
   ```

3. If the new kind requires custom field extraction (beyond the generic annotation key map), add enrichment logic in `normalizer.py:_enrich_call_node` (for structural nodes) or extend `_ANN_KEY_MAP` (for annotation fields).

### To suppress a kind silently

Map it to `None`:

```python
"legacy_event": None,   # silently skipped; no error raised
```

### Kinds absent from the map

Any event whose `kind` is not in `KIND_TO_CLASS` raises `UnknownSpanBoundaryError` at normalization time. This is intentional: unrecognised kinds are a data quality issue and should be either mapped or suppressed explicitly.

---

*See also: [normalization.md](normalization.md) for the full two-phase pipeline reference, [steps.md](steps.md#run_verify_events) for the `run_verify_events` API, and [ontology.md](ontology.md) for the MAS ontology class hierarchy.*
