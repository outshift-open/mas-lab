# Normalization Pipeline — `mas.library.kg.observability.native`

**Document:** `mas-lab-internal/library-kg/docs/normalization.md`  
**Scope:** Canonical reference for how native `events.jsonl` traces are converted into KG nodes and edges. Implementer-grade detail; accurate to `normalizer.py` and `mappings.py` as of 2026-07-07.

See also: [ontology.md](ontology.md) · [steps.md](steps.md) · [neo4j.md](neo4j.md)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Normalization Modes and Controls](#2-normalization-modes-and-controls)
3. [Runtime Properties](#3-runtime-properties)
4. [Event → KG Mapping Table](#4-event--kg-mapping-table)
5. [Synthesised Nodes and Edges](#5-synthesised-nodes-and-edges)
6. [Node Attributes Reference](#6-node-attributes-reference)
7. [Edge Type Reference](#7-edge-type-reference)
8. [Layer Defaults and Control](#8-layer-defaults-and-control)
9. [Node ID Stability](#9-node-id-stability)

---

## 1. Overview

The normalization pipeline converts a stream of native MAS observability events (an `events.jsonl` file or an in-memory list of dicts) into a structured knowledge graph consisting of typed nodes and directed edges.

OTel telemetry is treated as input/provenance for this pipeline, not as a
materialized node layer in the KG output. In particular, normalization does not
emit `Span` nodes. OTel linkage is carried as execution-node provenance
attributes (`sourceRecordIds`), while structural KG validation
uses `mas-ontology.ttl` + KG/lab extensions (not `otel-ontology.ttl`).

The pipeline runs in **two logical phases**:

### Phase 1 — Annotation (`normalize_events`)

**Complexity:** O(1) per event. No look-ahead required.

`normalize_events(events, ontology, run_id, **layer_flags)` iterates the event list once and:

1. Applies **layer filtering** — events whose `kind` belongs to a disabled layer's `LAYER_KINDS` set are dropped before any further processing.
2. Calls `_class_for_event(event)` which performs a hash-map lookup in `KIND_TO_CLASS` (imported from `native/mappings.py`) to assign `mas_class`. Suppressed kinds (mapped to `None`) receive `mas_class = "ExecutionElement"` as a sentinel, which causes `extract_graph` to skip them. Kinds absent from `KIND_TO_CLASS` raise `UnknownSpanBoundaryError` internally.
3. Looks up the ontology index (`_OntologyIndex`) to annotate each event with `mas_uri`, `span_level`, and `mas_icon`.
4. Validates that structural call events (anything not `CallAnnotation`, `ContextContribution`, `Worker`, or `ExecutionElement`) carry a `call_id`. Raises `MissingCallIdError` internally if absent.

Both of these are **observability gaps, not fatal errors**: `normalize_events` takes a `strict: bool = False` parameter. By default it catches `UnknownSpanBoundaryError` and `MissingCallIdError`, logs a `WARNING` (deduplicated per distinct gap so one bad mapping doesn't spam thousands of near-identical lines), drops just that one event, and continues normalizing the rest of the trace. Pass `strict=True` (e.g. in CI conformance checks of the mapping tables) to have either exception propagate instead.
5. Sets `run_id` on each event.
6. Calls `_enrich_parent_call_ids(normalized)` — a **single forward scan** that injects `parent_call_id` on `execution_start` events whose `parent_call_id` is absent, using the `call_id` of the currently-active `execution_start` of the `source_agent_id` from a preceding `routing` event. This pass is O(1) amortised per event (dict operations on `active_exec` and `pending_parent`).

### Phase 2 — Graph Extraction (`extract_graph`)

**Complexity:** O(n log n) total, dominated by the containment-inference sort.

`extract_graph(normalized, session_id_override=None)` folds the annotated event list into KG nodes and edges via:

1. **Main event loop** — upserts call nodes from `*_start`/`*_end` pairs, collects raw annotation/ContextContribution events, synthesises `ThinkingCall` nodes on `llm_call_end`, and emits `callsAgent` edges for delegate-tool calls.
2. **`_fix_context_assembly_outputs`** — backfills `ProcessingCall.processingOutput` from sibling `LLMCall.prompt` when the runtime emitted the literal string `"assembled"`.
3. **`_fix_empty_llm_completions`** — synthesises `LLMCall.completion` from subsequent `ToolCall` nodes when the LLM responded with tool-use only (empty `content`).
4. **`_resolve_annotation_edges`** — resolves each `CallAnnotation` or deferred `ContextContribution` node to its tightest enclosing call by timestamp containment and agent matching. Emits `annotates` or `contributesTo` edges.
5. **Session / Run / Agent nodes** — created from collected `run_ids` and `agent_ids`.
6. **`hasCall` and `executedBy` edges** — emitted for every call node.
7. **`_infer_contains_edges`** — O(n log n) sweep-line algorithm; sorts all timed call nodes by `(startTime ASC, endTime DESC)` then runs a stack-based enclosure check.
8. **`_synthesize_processing_calls`** — for each `AgentCall` with LLM children but no `ProcessingCall` child, synthesises a `ProcessingCall` with `processingName="system_prompt_injection"`.
9. **`_synthesize_states_and_transitions`** — creates `State` and `Transition` nodes for `AgentCall`, `LLMCall`, `ToolCall`, and `ProcessingCall` nodes with content; chains consecutive transitions with `leadsTo` edges.
10. **`_derived_from_edges`** — emits `derivedFrom` edges connecting child `ContextContribution` nodes to their parents via `parents[]`.
11. **`_extract_catalog_layer`** — derives `Tool`, `LLM`, `Skill`, `Processing` catalog nodes with `ofToolType`, `ofLLMType`, `invokesSkill`, `invokesProcessing` edges.

---

## 2. Normalization Modes and Controls

`library-kg` currently supports two normalization entry modes:

1. **Native events** (`events.jsonl`)
	 - Entry point: `build_kg_document(...)` / `build_kg_from_events_path(...)`
	 - Code path: `normalize_events(...)` -> `extract_graph(...)`
	 - Best fit when runtime-native telemetry already carries MAS-specific fields such as `call_id`, `parent_call_id`, `agent_id`, `run_id`, and layer-specific payloads.

2. **OTel spans**
	 - Entry point: `build_kg_from_otel_spans(...)`
	 - Code path: `convert_spans_to_events(...)` -> `build_kg_document(...)`
	 - Best fit when input is OpenClaw ClickHouse export or ioa_observe / MAS SDK span JSON.

### 2.1 Current controls inside `library-kg`

At the `library-kg` API boundary, the controls that exist today are:

| Control | Where | Meaning |
|---|---|---|
| `strict` | `normalize_events(...)`, `build_kg_document(...)`, `build_kg_from_otel_spans(...)` | Raise on observability gaps instead of logging and skipping malformed inputs. |
| `synthesize_llm_gaps` | `convert_spans_to_events(...)` | Enable the OTel compatibility pass that synthesizes missing `llm_call_start/end` events when the source trace lacks explicit LLM child spans. |
| `include_normalization_provenance` | `build_kg_document(...)`, `build_kg_from_otel_spans(...)`, `build_kg_from_events_path(...)` | Optional metadata switch (default `false`) to include normalization-path + heuristics provenance fields in `doc.metadata`. |
| `include_trajectory` / `include_provenance` / `include_governance` / `include_infrastructure` | `build_kg_document(...)` and callers | Select which ontology layers participate in normalization. |

### 2.2 Relationship to upstream `allow_heuristics` and `strict`

The higher-level telemetry contract now being introduced upstream uses two names:

| Upstream attribute | Intended effect at `library-kg` boundary |
|---|---|
| `allow_heuristics` | Allow compatibility recovery only on the OTel path. In the current `library-kg` codebase, the concrete control is `synthesize_llm_gaps` on `convert_spans_to_events(...)`. Native normalization does not accept heuristics. |
| `strict` | Fail when required source data is missing instead of silently degrading or skipping. This is the single strictness control used by both paths. |

In other words, the integration contract should translate as follows today:


- **Native path**
	- native normalization should be direct and non-heuristic.
	- strictness is handled by the same `strict=True` control as the rest of the pipeline.

- **OTel path, extended OTel**
	- `allow_heuristics=false` should be viable when the span stream already carries the required MAS attributes.
	- `strict=True` should call `convert_spans_to_events(..., strict=True)` and avoid heuristic recovery passes.

- **OTel path, standard OTel**
	- `allow_heuristics=true` may still be needed for compatibility, especially for missing LLM child spans.
	- `strict=True` should fail on missing required information rather than produce partial structural output silently.

### 2.3 Where heuristics still exist today

The current `library-kg` module still contains a small number of recovery/synthesis steps:

- `_fix_context_assembly_outputs(...)` backfills `ProcessingCall.processingOutput` from sibling `LLMCall.prompt` content.
- `_fix_empty_llm_completions(...)` synthesizes `LLMCall.completion` from following tool-use output when the LLM content is empty.
- `convert_spans_to_events(..., synthesize_llm_gaps=True)` synthesizes missing LLM start/end pairs on the OTel path.

These are compatibility mechanisms. They are useful for incomplete traces, but the target design remains:

- native telemetry should normalize directly from explicit source fields,
- extended OTel should normalize directly from explicit source fields,
- standard OTel may use heuristics only when explicitly allowed.

### 2.4 Provenance fields on nodes and document metadata

- `sourceRecordIds` is the generic ordered provenance field on `ExecutionElement` nodes.
- Normalization uses a canonical `record_id` field per path:
	- native path: `record_id = event_id`
	- OTel path: `record_id = span_id`
- Semantics: first ID created the node; later IDs updated its attributes.
- Document-level normalization provenance metadata is optional and disabled by default (`include_normalization_provenance=false`) to avoid payload growth.

---

## 3. Runtime Properties

| Property | Verdict | Detail |
|---|---|---|
| Real-time / streaming | ⚠ Partial | See below |
| Stateless | ✓ Holds | See below |
| O(1) per event | ⚠ Partial | See below |
| Resilience to duplicates | ✓ Holds | See below |
| Resilience to out-of-order | ⚠ Partial | See below |

### Real-time / streaming ⚠

The **annotation phase** (`normalize_events`) is truly real-time: O(1) per event, each enriched event can be emitted immediately, no look-ahead needed.

**`extract_graph` is a batch function** — it requires the complete event list before it can produce a correct graph because:

- `_fix_context_assembly_outputs` backfills `ProcessingCall.processingOutput` from a sibling `LLMCall` that arrives *after* the processing end event.
- `_fix_empty_llm_completions` synthesises LLM completions from `ToolCall` events that arrive *after* the LLM end event.
- `_infer_contains_edges` sorts all timed nodes before the sweep-line — requires the full set.
- `_synthesize_states_and_transitions` builds `leadsTo` chains across the full transition set.

**Verdict:** Annotation phase is real-time. Graph extraction is batch (requires full trace). A streaming-first implementation would buffer events until `*_end` is received for each call and defer cross-call backfills to a compaction step at trace close.

### Stateless ✓

The normalizer has no persistent mutable state across invocations. The module-level `_ontology_cache` is a **read-only, process-lifetime cache** keyed by resolved TTL path — it is populated on first use and never mutated thereafter. Within a trace, `extract_graph` accumulates `call_nodes`, `run_ids`, and `agent_ids` as working state local to the call frame, discarded on return.

**Verdict:** Stateless across traces. Necessary within-trace accumulation is bounded by O(n) memory.

### O(1) per event ⚠

The annotation loop in `normalize_events` is O(1) per event (hash-map lookups in `KIND_TO_CLASS` and the ontology index). `_enrich_parent_call_ids` is O(1) amortised per event (dict operations on `active_exec` and `pending_parent`).

The post-processing passes in `extract_graph` are not O(1):

| Pass | Complexity |
|---|---|
| `_infer_contains_edges` | O(n log n) — sort + O(n) stack sweep |
| `_synthesize_states_and_transitions` | O(n) nodes + O(n) leadsTo chaining per session |
| `_resolve_annotation_edges` | O(n × m) where m = avg call_nodes per agent |
| `_synthesize_processing_calls` | O(n) |
| `_fix_context_assembly_outputs` | O(n) |
| `_fix_empty_llm_completions` | O(n) |
| `_extract_catalog_layer` | O(n) |

**Verdict:** Annotation is O(1) per event. Full normalization is O(n log n) dominated by the containment-inference sort.

### Resilience to duplicates ✓

Duplicate `*_start` events (same `call_id`, same `kind`, before the matching `*_end`) are detected in the main loop — when `kind.endswith("_start")` and the node already exists with `startTime` set but no `endTime`, the duplicate is **converted to a `CallAnnotation` point node** rather than dropped or overwriting the original. Annotation node IDs are derived from `uuid5(run_id|agent_id|kind|timestamp|span_id)[:16]`, making them deterministic. Duplicate annotations with the same identity key are idempotent through `setdefault`.

Duplicate `*_end` events overwrite the node's `status`, `endTime`, and output fields (last-writer-wins). This is acceptable because end events carry terminal attributes and the final end event is authoritative.

**Verdict:** Resilient to duplicate starts (converted to annotations). Duplicate ends overwrite (last writer wins — acceptable).

### Resilience to out-of-order events ⚠

| Mechanism | Order-sensitive? |
|---|---|
| `_infer_contains_edges` sweep-line | ✓ Order-insensitive — sorts before sweep |
| `_synthesize_states_and_transitions` leadsTo | ✓ Order-insensitive — sorts by `transitionTimestamp` |
| `_enrich_parent_call_ids` routing inference | ⚠ Ordering-sensitive for delegation |
| Main event loop `*_start`/`*_end` pairing | ✓ Resilient — `setdefault` upsert pattern |

For `_enrich_parent_call_ids`: routing events must arrive before the `execution_start` of the target agent for `parent_call_id` injection to succeed. If a routing event arrives late, `parent_call_id` is not injected and the node appears as a root in the call tree. This is **graceful degradation** — no error is raised and the graph remains structurally valid.

**Verdict:** Containment and trajectory inference are order-insensitive. Routing-based delegation inference assumes ordered arrival; late routing events degrade gracefully.

---

## 3. Event → KG Mapping Table

The authoritative mapping is in `native/mappings.py:KIND_TO_CLASS`. The table below documents every entry.

### Core L0 — Structural (start/end pairs)

| Event Kind | Layer | KG Class | Pair Type | Key Fields Read | Nodes Created/Updated | Edges Created | Notes |
|---|---|---|---|---|---|---|---|
| `tool_call_start` | Core L0 | `ToolCall` | start | `tool_name`, `arguments`, `tool_call_id` | Upsert `ToolCall` node | `hasCall`, `executedBy` | `network_call_*` also maps to `ToolCall` |
| `tool_call_end` | Core L0 | `ToolCall` | end | `status`, `output`, `result` | Update `ToolCall.toolOutput`, `status` | — | |
| `network_call_start` | Core L0 | `ToolCall` | start | `tool_name`, `arguments` | Upsert `ToolCall` node | `hasCall`, `executedBy` | Treated identically to `tool_call_start` |
| `network_call_end` | Core L0 | `ToolCall` | end | `status`, `output` | Update `ToolCall.toolOutput`, `status` | — | |
| `llm_call_start` | Core L0 | `LLMCall` | start | `model`, `messages`, `input`, `prompt` | Upsert `LLMCall` node | `hasCall`, `executedBy` | `messages` list formatted via `_format_messages` |
| `llm_call_end` | Core L0 | `LLMCall` | end | `response`, `status`, `content` | Update `LLMCall.completion`, token counts, `finishReason`; synthesise `ThinkingCall` if `response.thinking` present | `hasThinking` (conditional) | Token fields read from `response.usage` |
| `execution_start` | Core L0 | `AgentCall` or `TaskCall` | start | `agent_id`, `input`, `boundary`, `agent_sequence` | Upsert `AgentCall` or `TaskCall` node | `hasCall`, `executedBy` | Becomes `TaskCall` when `boundary=TaskCall` |
| `execution_end` | Core L0 | `AgentCall` or `TaskCall` | end | `status`, `output` | Update `outputContent`, `status` | — | |
| `mas_call_start` | Core L0 | `MASCall` | start | `mas_name`, `mas_type` | Upsert `MASCall` node | `hasCall`, `executedBy` | |
| `mas_call_end` | Core L0 | `MASCall` | end | `status`, `output` | Update `outputContent`, `status` | — | |
| `rag_query_start` | Core L0 | `RAGQuery` | start | — | Upsert `RAGQuery` node | `hasCall`, `executedBy` | No class-specific start enrichment beyond base fields |
| `rag_query_end` | Core L0 | `RAGQuery` | end | `status` | Update `status` | — | |
| `memory_call_start` | Core L0 | `MemoryCall` | start | — | Upsert `MemoryCall` node | `hasCall`, `executedBy` | |
| `memory_call_end` | Core L0 | `MemoryCall` | end | `status` | Update `status` | — | |
| `memory_store_start` | Core L0 | `MemoryCall` | start | — | Upsert `MemoryCall` node | `hasCall`, `executedBy` | All memory variants map to the same class |
| `memory_store_end` | Core L0 | `MemoryCall` | end | `status` | Update `status` | — | |
| `memory_retrieve_start` | Core L0 | `MemoryCall` | start | — | Upsert `MemoryCall` node | `hasCall`, `executedBy` | |
| `memory_retrieve_end` | Core L0 | `MemoryCall` | end | `status` | Update `status` | — | |
| `processing_call_start` | Core L0 | `ProcessingCall` | start | `processing_name`, `processing_type`, `input` | Upsert `ProcessingCall` node | `hasCall`, `executedBy` | |
| `processing_call_end` | Core L0 | `ProcessingCall` | end | `status`, `output` | Update `processingOutput`, `status` | — | `_fix_context_assembly_outputs` may backfill if output is `"assembled"` |
| `workflow_transition_start` | Core L0 | `ProcessingCall` | start | `processing_name` | Upsert `ProcessingCall` node | `hasCall`, `executedBy` | No dedicated ontology class; modelled as ProcessingCall |
| `workflow_transition_end` | Core L0 | `ProcessingCall` | end | `status` | Update `status` | — | |
| `skill_execution_start` | Core L0 | `SkillCall` | start | `skill_name`, `input`, `skill_version` | Upsert `SkillCall` node | `hasCall`, `executedBy` | |
| `skill_execution_end` | Core L0 | `SkillCall` | end | `status`, `output` | Update `skillOutput`, `status` | — | |

### Core L0 — Annotation (point events, attached to enclosing call)

These events carry no `call_id`. They become `CallAnnotation` nodes resolved to their tightest enclosing structural call via `_resolve_annotation_edges`.

| Event Kind | Layer | KG Class | Type | Key Fields Read | Node Created | Edge Created | Notes |
|---|---|---|---|---|---|---|---|
| `routing` | Core L0 | `CallAnnotation` | point | `source_agent_id`, `target_agent_id`, `task`, `correlation_id` | `CallAnnotation` | `annotates` → enclosing call | Also feeds `_enrich_parent_call_ids` |
| `routing_result` | Core L0 | `CallAnnotation` | point | `source_agent_id`, `target_agent_id`, `status`, `correlation_id` | `CallAnnotation` | `annotates` → enclosing call | |
| `context_assembled` | Core L0 | `CallAnnotation` | point | — | `CallAnnotation` | `annotates` | Signals context assembly completion |
| `state_update_start` | Core L0 | `CallAnnotation` | point (pair) | `operation`, `target` | `CallAnnotation` | `annotates` | Paired but both become independent annotations |
| `state_update_end` | Core L0 | `CallAnnotation` | point (pair) | `status` | `CallAnnotation` | `annotates` | |
| `agent_communication_start` | Core L0 | `CallAnnotation` | point (pair) | `source_agent_id`, `target_agent_id`, `message_type` | `CallAnnotation` | `annotates` | |
| `agent_communication_end` | Core L0 | `CallAnnotation` | point (pair) | `status` | `CallAnnotation` | `annotates` | |
| `checkpoint_start` | Core L0 | `CallAnnotation` | point (pair) | — | `CallAnnotation` with `block="governance"` | `annotates` | |
| `checkpoint_end` | Core L0 | `CallAnnotation` | point (pair) | `status` | `CallAnnotation` with `block="governance"` | `annotates` | |
| `user_input` | User I/O | `CallAnnotation` | point | — | `CallAnnotation` | `annotates` | UI-layer event |
| `user_output` | User I/O | `CallAnnotation` | point | — | `CallAnnotation` | `annotates` | UI-layer event |
| `tool_result_injected` | User I/O | `CallAnnotation` | point | `tool_name` | `CallAnnotation` | `annotates` | Context provenance for tool result re-injection |

### L4 — Provenance

| Event Kind | Layer | KG Class | Type | Key Fields Read | Node Created | Edge Created | Notes |
|---|---|---|---|---|---|---|---|
| `context_part_contributed` | L4 Provenance | `ContextContribution` | point | `part_id`, `source`, `section_id`, `access_mechanism`, `cause_type`, `token_estimate`, `retained`, `content`, `llm_call_id`, `parents` | `ContextContribution` | `contributesTo` → LLMCall (by `llm_call_id` or timestamp fallback); `derivedFrom` → parent CPR nodes | Off by default (`include_provenance=False`) |

### L2 — Trajectory

| Event Kind | Layer | KG Class | Type | Key Fields Read | Node Created | Edge Created | Notes |
|---|---|---|---|---|---|---|---|
| `parallel_group_start` | L2 Trajectory | `ParallelGroup` | start | `call_id` | Upsert `ParallelGroup` node | `hasCall`, `executedBy` | Off by default (`include_trajectory=True` — note: trajectory IS on by default; these are included when `include_trajectory=True`) |
| `parallel_group_end` | L2 Trajectory | `ParallelGroup` | end | `status` | Update `status` | — | |
| `branch_start` | L2 Trajectory | `Branch` | start | `call_id` | Upsert `Branch` node | `hasCall`, `executedBy` | |
| `branch_end` | L2 Trajectory | `Branch` | end | `status` | Update `status` | — | |

> Note: `routing` and `routing_result` are also in the trajectory layer (see `LAYER_KINDS["trajectory"]`). They appear in the annotation table above but are suppressed when `include_trajectory=False`.

### L5 — Governance

All governance events become `CallAnnotation` nodes with `block="governance"` set, pending a dedicated `GovernanceEvent` ontology class.

| Event Kind | Layer | KG Class | Notes |
|---|---|---|---|
| `audit` | L5 Governance | `CallAnnotation` | |
| `policy_denial` | L5 Governance | `CallAnnotation` | |
| `policy_allow` | L5 Governance | `CallAnnotation` | |
| `budget_event` | L5 Governance | `CallAnnotation` | `budgetScope`, `amount` in `_ANN_KEY_MAP` |
| `transformation_event` | L5 Governance | `CallAnnotation` | |
| `control_intervention` | L5 Governance | `CallAnnotation` | `interventionType` in `_ANN_KEY_MAP` |
| `hitl_gate` | L5 Governance | `CallAnnotation` | |
| `governance_denied` | L5 Governance | `CallAnnotation` | `policyId`, `decision`, `reason`, `deniedCallId` |
| `governance_checked` | L5 Governance | `CallAnnotation` | |
| `obs_wrap_gov_authorize_start/end` | L5 Governance | `CallAnnotation` | Runtime wrapper events |
| `obs_wrap_gov_validate_start/end` | L5 Governance | `CallAnnotation` | Runtime wrapper events |
| `governance_authorize_start/end` | L5 Governance | `CallAnnotation` | |
| `governance_validate_start/end` | L5 Governance | `CallAnnotation` | |

### L1 — Infrastructure

| Event Kind | Layer | KG Class | Type | Key Fields Read | Node Created | Edge Created | Notes |
|---|---|---|---|---|---|---|---|
| `infrastructure_info` | L1 Infrastructure | `Worker` | point | (worker attributes) | `Worker` | — | Off by default (`include_infrastructure=False`) |

### Suppressed (mapped to `None`)

These kinds are silently dropped. Events from old traces that emit them produce no KG nodes.

| Event Kind | Reason |
|---|---|
| `prompt_build_start/end` | Redundant with `llm_call_start.messages` |
| `user_response` | Redundant with `execution_end.output` |
| `human_interaction` | Legacy |
| `delegated_agent_output` | Legacy |
| `skills_check` | Governance extension only (legacy) |
| `object_upsert` | Domain-KG extension only |
| `object_link` | Domain-KG extension only |
| `object_model_event` | Domain-KG extension only |
| `user_input_request` | Not a call node |

---

## 4. Synthesised Nodes and Edges

These nodes and edges are **not directly produced by input events**. They are created by post-processing passes in `extract_graph`.

### Session Node

**Created by:** main loop in `extract_graph`, after processing all events.  
**One per** distinct `run_id`.  
**ID:** `session-{run_id}` (e.g. `session-run-abc123`).

`inputQuery` is derived from the outermost `MASCall.masName` or `MASCall.inputContent`, falling back to the outermost `AgentCall.inputContent` (the `AgentCall` with the earliest `startTime`). `startTime`/`endTime` are copied from the same outer call.

**Edges emitted:** `contains` → the `Run` node for the same `run_id`.

### Run Node

**Created by:** main loop.  
**One per** distinct `run_id`.  
**ID:** `run_id` itself (a runtime string such as `run-abc123def456`).  
**Purpose:** Legacy node retained for backward compatibility; the `Session` node is the preferred top-level container.

### Agent Node

**Created by:** main loop.  
**One per** distinct `agent_id` seen across all events.  
**ID:** `agent_id` string.

### `contains` Edges (Timestamp Enclosure)

**Created by:** `_infer_contains_edges`.  
**Algorithm:** Sweep-line. All timed call nodes are sorted by `(startTime ASC, endTime DESC)`. A stack tracks the active parent chain. For each node, expired parents (whose `endTime < current node's endTime`) are popped. The stack top, if any, is the tightest enclosing ancestor and receives a `contains` edge to the current node.  
**Complexity:** O(n log n).  
**Precondition:** Nodes must have both `startTime` and `endTime` set. Zero-duration ghost nodes (`startTime == endTime == 0.0`) are filtered out before the sort.

### `hasCall` Edges

**Created by:** main loop, after building `call_node_list`.  
**Edge:** `Run` → `CallNode` for every structural call node.  
Every call node, including synthesised `ProcessingCall` nodes added by `_synthesize_processing_calls`, receives a `hasCall` edge from its `runId` Run node.

### `executedBy` Edges

**Created by:** main loop.  
**Edge:** `CallNode` → `Agent`.  
Every call node with a non-empty `agentId` emits an `executedBy` edge to the corresponding `Agent` node.

### State and Transition Nodes

**Created by:** `_synthesize_states_and_transitions`.

For each qualifying call node, two `State` nodes and one `Transition` node are created:

| Call type | Condition | State IDs | Transition ID | Action type |
|---|---|---|---|---|
| `AgentCall` | `inputContent` or `outputContent` non-empty | `state-agent-{callId}-initial`, `state-agent-{callId}-final` | `trans-agent-{callId}` | `agent_delegation` |
| `LLMCall` | `prompt` or `completion` non-empty | `state-llm-{callId}-prompt`, `state-llm-{callId}-completion` | `trans-llm-{callId}` | `llm_call` |
| `ToolCall` | `toolArguments` or `toolOutput` non-empty | `state-tool-{callId}-args`, `state-tool-{callId}-result` | `trans-tool-{callId}` | `tool_call` |
| `ProcessingCall` | `inputContent` or `processingOutput` non-empty | `state-proc-{callId}-input`, `state-proc-{callId}-output` | `trans-proc-{callId}` | context processing kind or `context_assembly` |

**Edges per triple:** 5 edges — `hasInitialState`, `hasFinalState`, `fromState`, `toState`, `realizes`.

**`leadsTo` edges:** After all triples are built, `Transition` nodes are sorted by `transitionTimestamp` within each session. Consecutive pairs receive a `leadsTo` edge: `State_out(T_n)` → `State_in(T_{n+1})`. This enables full trajectory reconstruction without timestamp heuristics.

For `ToolCall` with a `barrierId`, the `Transition.edgeType` is `"parallel"` and `appliedOperator` is `"parallel_merge"`.

For `ProcessingCall`, the `Transition` node carries additional context metrics: `transitionDeltaType`, `contextTokensIn`, `contextTokensOut`, `contextTokensDelta`, `compressionRatio`, `contextStrategy`. The delta type is inferred from `processingName` via a built-in map (e.g. `context_truncation` → `"remove"`, `context_assembly` → `"add"`).

### Synthesised ProcessingCall (`_synthesize_processing_calls`)

**Created by:** `_synthesize_processing_calls`, called after `_infer_contains_edges`.

For each `AgentCall` that:
- Has at least one `LLMCall` child (determined from `contains` edges), AND
- Has no existing `ProcessingCall` child

A synthetic `ProcessingCall` is created with:
- `callId`: `synth-pc-{agentCallId}`
- `processingName`: `"system_prompt_injection"`
- `processingType`: `"prompt_engineering"`
- `startTime`: `agentCall.startTime`
- `endTime`: `firstLLMCall.startTime`
- `synthesised`: `True`

**Edges emitted:** `contains` (from `AgentCall` to the new node) and `hasCall` (from `Run` to the new node).

### ThinkingCall Node

**Created by:** main event loop on `llm_call_end` when `response.thinking` is non-empty.

- `callId`: `{llmCallId}-thinking`
- `node_type`: `ThinkingCall`
- `startTime`: same as parent `LLMCall.startTime`
- `endTime`: `llmStart + (llmEnd - llmStart) * 0.85` — thinking occupies the first 85% of the LLM call duration
- `thinkingContent`: the thinking text

**Edge emitted:** `hasThinking` from the parent `LLMCall` to the `ThinkingCall` node.

### Catalog Nodes (Tool, LLM, Skill, Processing)

**Created by:** `_extract_catalog_layer`.

One node per distinct name of each type:

| Node type | Distinct key | Source attribute | Edge type |
|---|---|---|---|
| `Tool` | `toolName` | `ToolCall.toolName` | `ofToolType` |
| `LLM` | `modelName` | `LLMCall.modelName` | `ofLLMType` |
| `Skill` | `skillName` | `SkillCall.skillName` | `invokesSkill` |
| `Processing` | `processingName` | `ProcessingCall.processingName` | `invokesProcessing` |

**ID pattern:** `catalog:{type}:{name}` (e.g. `catalog:tool:search_web`, `catalog:model:claude-sonnet-4-5`).

Each catalog node carries `callCount` (number of call nodes referencing that name) and `block="structural"`.

### `callsAgent` Edge

**Created by:** main event loop on `ToolCall` events.

When a `ToolCall.toolName` starts with `"delegate_to_"`, a `callsAgent` edge is emitted:
- `from_id`: the `ToolCall.callId`
- `to_id`: the agent name after stripping the `"delegate_to_"` prefix
- `to_type`: `"agent"`
- `tool_name`: the original tool name

---

## 5. Node Attributes Reference

### Session

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | Constant `"Session"` | |
| `id` | `f"session-{run_id}"` | |
| `sessionId` | `f"session-{run_id}"` | Alias for `id` |
| `executionId` | `f"exec-Session-{run_id}"` | |
| `runId` | `run_id` | |
| `inputQuery` | `MASCall.masName` or `MASCall.inputContent` or `AgentCall.inputContent` | From outermost call |
| `finalResponse` | `MASCall.outputContent` or `AgentCall.outputContent` | From outermost call |
| `startTime` | Outer call `startTime` | |
| `endTime` | Outer call `endTime` | |

### Run

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | Constant `"Run"` | |
| `id` | `run_id` string | |
| `runId` | `run_id` string | Alias |

### Agent

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | Constant `"Agent"` | |
| `id` | `agent_id` string | |
| `agentId` | `agent_id` string | Alias |

### MASCall

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"MASCall"` | |
| `id` / `callId` | `event.call_id` | Runtime UUID |
| `executionId` | `f"exec-MASCall-{call_id}"` | |
| `agentId` | `event.agent_id` | |
| `parentCallId` | `event.parent_call_id` | |
| `masName` | `event.mas_name` or `event.agent_id` | From start event |
| `masType` | `event.mas_type` | From start event |
| `outputContent` | `event.output` or `event.payload` | From end event |
| `startTime` | `event.timestamp` (start) | |
| `endTime` | `event.timestamp` (end) | |
| `status` | `event.status` | From end event |
| `runId` | `event.run_id` | |
| `masUri` | Ontology lookup | |
| `spanLevel` | Ontology lookup | |
| `sourceRecordIds` | ordered `event.span_id` list | Creator record first, then updater records |

### AgentCall

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"AgentCall"` or `"TaskCall"` | `TaskCall` when `event.boundary == "TaskCall"` |
| `id` / `callId` | `event.call_id` | Runtime UUID |
| `executionId` | `f"exec-AgentCall-{call_id}"` | |
| `agentId` | `event.agent_id` | |
| `agentName` | `event.agent_id` or `node.agentId` | Set from start; post-pass fills missing |
| `agentType` | `event.agent_type` | From start event |
| `parentCallId` | `event.parent_call_id` | May be injected by `_enrich_parent_call_ids` |
| `inputContent` | `event.input` or `event.payload` | From start event |
| `outputContent` | `event.output` or `event.payload` | From end event |
| `agentSequence` | `int(event.agent_sequence)` | Optional, from start event |
| `startTime` | `event.timestamp` (start) | |
| `endTime` | `event.timestamp` (end) | |
| `status` | `event.status` | From end event |
| `runId` | `event.run_id` | |
| `sourceRecordIds` | ordered `event.span_id` list | |

### LLMCall

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"LLMCall"` | |
| `id` / `callId` | `event.call_id` | |
| `agentId` | `event.agent_id` | |
| `llmName` | `event.llm_name` or `event.agent_id` | From start event |
| `modelName` | `event.model` or `response.model` | From start or end event |
| `prompt` | `event.input` or `event.prompt` or formatted `event.messages` | From start event |
| `completion` | Extracted from `event.response` | From end event; synthesised by `_fix_empty_llm_completions` if empty |
| `thinking` | `event.response.thinking` | From end event; triggers `ThinkingCall` synthesis |
| `promptTokenCount` | `event.response.usage.prompt_tokens` or `.input_tokens` | |
| `completionTokenCount` | `event.response.usage.completion_tokens` or `.output_tokens` | |
| `totalTokenCount` | `event.response.usage.total_tokens` | |
| `responseId` | `event.response.id` | |
| `finishReason` | `event.response.choices[0].finish_reason` | |
| `startTime` / `endTime` / `status` / `runId` / `sourceRecordIds` | Standard | |

### ToolCall

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"ToolCall"` | Also used for `network_call_*` events |
| `id` / `callId` | `event.call_id` | |
| `agentId` | `event.agent_id` | |
| `toolName` | `event.tool_name` | From start event |
| `toolCallId` | `event.tool_call_id` | From start event |
| `toolArguments` | `json.dumps(event.tool_arguments or event.arguments or event.parameters or {})` | From start event |
| `toolOutput` | `event.output` or `event.result` | From end event |
| `startTime` / `endTime` / `status` / `runId` / `sourceRecordIds` | Standard | |

### MemoryCall

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"MemoryCall"` | |
| `id` / `callId` | `event.call_id` | |
| `agentId` | `event.agent_id` | |
| `startTime` / `endTime` / `status` / `runId` | Standard | No class-specific enrichment beyond base |

### RAGQuery

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"RAGQuery"` | |
| `id` / `callId` | `event.call_id` | |
| `agentId` | `event.agent_id` | |
| `startTime` / `endTime` / `status` / `runId` | Standard | No class-specific enrichment beyond base |

### ProcessingCall

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"ProcessingCall"` | |
| `id` / `callId` | `event.call_id` | Synthesised nodes use `synth-pc-{agentCallId[:8]}` |
| `agentId` | `event.agent_id` | |
| `processingName` | `event.processing_name` or `kindBase` | From start event |
| `processingType` | `event.processing_type` | From start event |
| `inputContent` | `event.input` or `event.payload` | From start event |
| `processingOutput` | `event.output` | From end event; may be backfilled by `_fix_context_assembly_outputs` |
| `outputContent` | Same as `processingOutput` after backfill | |
| `synthesised` | `True` (only on synthesised nodes) | |
| `startTime` / `endTime` / `status` / `runId` | Standard | |

### SkillCall

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"SkillCall"` | |
| `id` / `callId` | `event.call_id` | |
| `agentId` | `event.agent_id` | |
| `skillName` | `event.skill_name` or `event.processing_name` or `kindBase` | From start event |
| `skillInput` | `event.input` or `event.payload` | From start event |
| `skillOutput` | `event.output` or `event.result` | From end event |
| `skillVersion` | `event.skill_version` | Optional |
| `startTime` / `endTime` / `status` / `runId` | Standard | |

### ParallelGroup

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"ParallelGroup"` | |
| `id` / `callId` | `event.call_id` | |
| Standard base attributes | | Only included when `include_trajectory=True` |

### Branch

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"Branch"` | |
| `id` / `callId` | `event.call_id` | |
| Standard base attributes | | Only included when `include_trajectory=True` |

### Worker (L1 Infrastructure)

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"Worker"` | |
| Worker-specific attributes | `infrastructure_info` event fields | Only included when `include_infrastructure=True` |

### CallAnnotation

Annotation nodes carry standard identity fields plus a payload mapped from the raw event via `_ANN_KEY_MAP`:

| Node Attribute | Raw Event Field | Notes |
|---|---|---|
| `node_type` | `"CallAnnotation"` | |
| `id` / `annotationId` | `f"ann-{_annotation_id(ev, run_id)}"` | UUID5-derived, 16 hex chars |
| `agentId` | `event.agent_id` or `event.source_agent_id` | Fallback for routing events |
| `kind` | `event.kind` | Original event kind |
| `timestamp` | `event.timestamp` | |
| `runId` | `event.run_id` | |
| `callId` | `event.call_id` | Only on duplicate-start annotations |
| `parentCallId` | `event.parent_call_id` | Only on duplicate-start annotations |
| `sourceAgentId` | `event.source_agent_id` | Via `_ANN_KEY_MAP` |
| `targetAgentId` | `event.target_agent_id` | Via `_ANN_KEY_MAP` |
| `task` | `event.task` | Via `_ANN_KEY_MAP` |
| `correlationId` | `event.correlation_id` | Via `_ANN_KEY_MAP` |
| `status` | `event.status` | Via `_ANN_KEY_MAP` |
| `segments` | `event.segments` | Via `_ANN_KEY_MAP` |
| `totalTokens` | `event.total_tokens` | Via `_ANN_KEY_MAP` |
| `operation` | `event.operation` | Via `_ANN_KEY_MAP` |
| `target` | `event.target` | Via `_ANN_KEY_MAP` |
| `from` | `event.from` | Via `_ANN_KEY_MAP` |
| `to` | `event.to` | Via `_ANN_KEY_MAP` |
| `messageType` | `event.message_type` | Via `_ANN_KEY_MAP` |
| `policyId` | `event.policy_id` | Via `_ANN_KEY_MAP` |
| `decision` | `event.decision` | Via `_ANN_KEY_MAP` |
| `reason` | `event.reason` | Via `_ANN_KEY_MAP` |
| `deniedCallId` | `event.denied_call_id` | Via `_ANN_KEY_MAP` |
| `budgetScope` | `event.budget_scope` | Via `_ANN_KEY_MAP` |
| `amount` | `event.amount` | Via `_ANN_KEY_MAP` |
| `interventionType` | `event.intervention_type` | Via `_ANN_KEY_MAP` |
| `annotationKind` | `event.kind` | Set for governance and checkpoint events |
| `block` | `"governance"` | Set for governance and checkpoint events |

### ContextContribution (L4)

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"ContextContribution"` | |
| `id` | `f"cpr-{part_id}"` | |
| `masUri` | `_MAS_NS + "ContextContribution"` | |
| `agentId` | `event.agent_id` | |
| `partId` | `event.part_id` or `_annotation_id(ev, run_id)` | |
| `parents` | `event.parents` or `event.provenance.parents` | For `derivedFrom` edges |
| `source` | `event.source` | Section/document source |
| `sectionId` | `event.section_id` | |
| `sourceType` | `event.source_type` | Default `"unknown"` |
| `accessMechanism` / `mechanism` | `event.access_mechanism` | Default `"inject"` |
| `cause` | `event.cause` | Default `"context_manager"` |
| `causeType` | `event.cause_type` | Default `"deterministic"` |
| `tokenEstimate` | `event.token_estimate` | Default `0` |
| `retained` | `event.retained` | Default `True` |
| `evictionReason` | `event.eviction_reason` | Only when `retained=False`, default `"budget_exceeded"` |
| `sensitivity` | `event.sensitivity` | Optional |
| `content` | `event.content` or `event.content_preview` | |
| `contentPreview` | First 200 chars of content | |
| `timestamp` | `event.timestamp` | |
| `runId` | `event.run_id` | |

### State

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"State"` | |
| `id` / `stateNodeId` | See [Section 8](#8-node-id-stability) | |
| `contentHash` | `sha256(content)` | 64 hex chars; stable across sessions for same content |
| `content` | Call node content field (prompt, args, etc.) | Truncated to `_STATE_CONTENT_MAX_LEN = 8000` chars |
| `semanticType` | `"initial"`, `"final"`, `"prompt"`, `"completion"`, `"args"`, `"result"`, `"input"`, `"output"` | |
| `sessionId` | `f"session-{runId}"` | |
| `sourceCallId` | Parent call's `callId` | |
| `deltaType` | Context delta type | ProcessingCall and ToolCall states only |
| `contextWindowSize` | Token count | ProcessingCall states only |

### Transition

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"Transition"` | |
| `id` / `transitionId` | See [Section 8](#8-node-id-stability) | |
| `sessionId` | `f"session-{runId}"` | |
| `fromState` | Initial state node ID | |
| `toState` | Final state node ID | |
| `edgeType` | `"sequential"` or `"parallel"` | Parallel for ToolCalls with `barrierId` |
| `realizesCallId` | Call node `callId` | |
| `actionType` | e.g. `"agent_delegation"`, `"llm_call"`, `"tool_call"`, processing kind | |
| `appliedOperator` | e.g. `"sequential_compose"`, `"parallel_merge"`, `"context_transform"` | |
| `transitionTimestamp` | Call node `startTime` | |
| `transitionDuration` | `endTime - startTime` | Float seconds or `None` |
| `transitionDeltaType` | Context delta type | ProcessingCall transitions only |
| `contextTokensIn` / `Out` / `Delta` | Token metrics | ProcessingCall transitions only |
| `compressionRatio` | Computed or explicit | ProcessingCall transitions only |
| `contextStrategy` | `event.contextStrategy` | ProcessingCall transitions only |
| `barrierId` | `node.barrierId` | Parallel ToolCall transitions only |

### ThinkingCall (synthesised)

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"ThinkingCall"` | |
| `id` / `callId` | `f"{llmCallId}-thinking"` | |
| `executionId` | `f"ThinkingCall/{callId}"` | |
| `agentId` | Parent LLMCall's `agentId` | |
| `parentCallId` | Parent LLMCall's `callId` | |
| `kindBase` | `"thinking_call"` | |
| `masUri` | `_MAS_NS + "ThinkingCall"` | |
| `spanLevel` | `"thinking"` | |
| `runId` | Parent LLMCall's `runId` | |
| `startTime` | Parent LLMCall's `startTime` | |
| `endTime` | `llmStart + (llmEnd - llmStart) * 0.85` | First 85% of LLM call duration |
| `thinkingContent` | `event.response.thinking` | |
| `status` | `"success"` | Fixed |

### Catalog Nodes (Tool, LLM, Skill, Processing)

| Attribute | Source | Notes |
|---|---|---|
| `node_type` | `"Tool"` / `"LLM"` / `"Skill"` / `"Processing"` | |
| `id` | `f"catalog:{type}:{name}"` | |
| `name` | Distinct `toolName` / `modelName` / `skillName` / `processingName` | |
| `callCount` | Number of call nodes referencing this name | |
| `block` | `"structural"` | |
| `masUri` | `_MAS_NS + node_type` | |

---

## 6. Edge Type Reference

| Edge Type | From Node Type | To Node Type | Created By | Notes |
|---|---|---|---|---|
| `contains` | `Session` | `Run` | Main loop (session→run) | Session contains its Run(s) |
| `contains` | Any call node | Any call node | `_infer_contains_edges` | Timestamp enclosure; O(n log n) |
| `contains` | `AgentCall` | Synthesised `ProcessingCall` | `_synthesize_processing_calls` | Injection gate node |
| `hasCall` | `Run` | Any call node | Main loop | Every call node gets this edge |
| `hasCall` | `Run` | Synthesised `ProcessingCall` | `_synthesize_processing_calls` | |
| `executedBy` | Any call node | `Agent` | Main loop | Only when `agentId` is non-empty |
| `callsAgent` | `ToolCall` | `Agent` | Main loop | When `toolName.startswith("delegate_to_")` |
| `annotates` | `CallAnnotation` | Any call node | `_resolve_annotation_edges` | Timestamp + agent containment |
| `contributesTo` | `ContextContribution` | `LLMCall` | Main loop or `_resolve_annotation_edges` | By `llm_call_id` or timestamp fallback |
| `derivedFrom` | `ContextContribution` | `ContextContribution` | `_derived_from_edges` | Parent CPR DAG via `parents[]` |
| `hasInitialState` | Any call node | `State` | `_synthesize_states_and_transitions` | |
| `hasFinalState` | Any call node | `State` | `_synthesize_states_and_transitions` | |
| `fromState` | `Transition` | `State` | `_synthesize_states_and_transitions` | |
| `toState` | `Transition` | `State` | `_synthesize_states_and_transitions` | |
| `realizes` | `Transition` | Call node | `_synthesize_states_and_transitions` | |
| `leadsTo` | `State` | `State` | `_synthesize_states_and_transitions` | `toState(T_n)` → `fromState(T_{n+1})`, same session |
| `hasThinking` | `LLMCall` | `ThinkingCall` | Main loop (on `llm_call_end`) | When `response.thinking` non-empty |
| `ofToolType` | `ToolCall` | `Tool` (catalog) | `_extract_catalog_layer` | |
| `ofLLMType` | `LLMCall` | `LLM` (catalog) | `_extract_catalog_layer` | |
| `invokesSkill` | `SkillCall` | `Skill` (catalog) | `_extract_catalog_layer` | |
| `invokesProcessing` | `ProcessingCall` | `Processing` (catalog) | `_extract_catalog_layer` | |

---

## 7. Layer Defaults and Control

`normalize_events` accepts four boolean layer flags that control which event kinds reach the KG. The flags are checked before any ontology lookup — filtered events are dropped entirely and produce no nodes or edges.

| Flag | Default | `LAYER_KINDS` members | Effect when `False` |
|---|---|---|---|
| `include_infrastructure` | `False` | `infrastructure_info` | Worker nodes not created |
| `include_trajectory` | `True` | `parallel_group_start`, `parallel_group_end`, `branch_start`, `branch_end`, `routing`, `routing_result` | Parallel/branch topology nodes not created; routing annotations suppressed (delegation inference in `_enrich_parent_call_ids` still runs on the pre-filtered list — so routing events are read for structural inference before the filter is applied) |
| `include_provenance` | `False` | `context_part_contributed` | ContextContribution nodes not created |
| `include_governance` | `False` | `audit`, `policy_denial`, `policy_allow`, `budget_event`, `transformation_event`, `control_intervention`, `hitl_gate`, `governance_denied`, `governance_checked`, all `obs_wrap_gov_*` and `governance_*` variants | Governance CallAnnotation nodes not created |

**Important:** The structural core (all `*_start`/`*_end` call pairs mapped to non-`None` classes) and the annotation layer (`routing`, `context_assembled`, `state_update_*`, `agent_communication_*`, `checkpoint_*`, `user_input`, `user_output`, `tool_result_injected`) are **always active** and cannot be suppressed via these flags. Only the four optional layers above have flags.

### 7.1 Terminology Alignment: runtime "layer" vs ontology `block` / `layer`

Three terms coexist and must not be mixed:

- **Normalization feature layers** (`include_infrastructure`, `include_trajectory`, `include_provenance`, `include_governance`): runtime filters over event kinds (`LAYER_KINDS`).
- **Ontology `block`** (`mas:block` class annotation, `maslab:block` instance property): coarse graph partition used for browsing/validation (`structural`, `execution`, `trajectory`, and extension-specific values).
- **Ontology `layer`** (`mas:layer`): trajectory-enrichment stage (`normalized`, `syntactic`, `semantic`, `symbolic`, `causal`, etc.), primarily for trajectory-derived classes.

| Concept | Where defined | Scope | Examples |
|---|---|---|---|
| Feature layer flags | `native/mappings.py:LAYER_KINDS` + `normalize_events(...)` | Runtime ingestion control | `include_provenance=False` drops `context_part_contributed` events |
| `mas:block` / `maslab:block` | `mas-ontology.ttl` + `experiment-orchestration.ttl` | Node partition vocabulary | `execution`, `trajectory`, `structural` |
| `mas:layer` | `mas-ontology.ttl` + extension ontologies | Trajectory enrichment stage | `normalized`, `semantic`, `causal` |

### 7.2 Where classes live (single-source ontology package)

Some node classes used by normalization are declared outside `mas-ontology.ttl` in extension TTLs. This is expected.

| Class family | Primary TTL |
|---|---|
| Core execution and trajectory roots (`Session`, `Run`, `State`, `Transition`, call classes) | `mas-ontology.ttl` |
| Provenance/infrastructure bridge classes (`ContextContribution`, `Worker`) | `mas-kg-extension.ttl` |
| Parallel/branch trajectory enrichments | `mas-ontology.ttl` and/or interpretability extensions depending on class |
| Semantic/causal trajectory enrichment classes | `interpretability-ontology.ttl` |

Normalization therefore resolves ontology from the `oxp-ontology` package and may load multiple TTL modules, not a single file snapshot.

Note on `include_trajectory` and routing: `_enrich_parent_call_ids` is called on the already-filtered list. If `include_trajectory=False`, routing events are dropped before `_enrich_parent_call_ids` runs, so delegation inference via routing will not inject `parent_call_id` on sub-agent `execution_start` events. The delegation tree degrades to flat roots.

---

## 8. Node ID Stability

Deterministic, stable IDs are critical for round-trip idempotency when re-normalizing the same trace or writing to Neo4j with `MERGE`.

| Node type | ID pattern | Example | Notes |
|---|---|---|---|
| Structural call nodes | `call_id` (runtime UUID preserved as-is) | `3f4a1b2c-...` | Runtime emits a UUID per call; `*_start` and `*_end` share the same `call_id` |
| Annotation point nodes | `ann-{uuid5(run_id|agent_id|kind|timestamp|span_id)[:16]}` | `ann-a1b2c3d4e5f6a7b8` | Deterministic from event identity; idempotent across re-normalizations |
| ContextContribution nodes | `cpr-{part_id}` | `cpr-abc123` | `part_id` from event; fallback to same uuid5 derivation as annotations |
| State nodes (AgentCall) | `state-agent-{callId}-initial` / `-final` | `state-agent-3f4a1b2c-...-initial` | Stable because `callId` is stable |
| State nodes (LLMCall) | `state-llm-{callId}-prompt` / `-completion` | `state-llm-3f4a...-prompt` | |
| State nodes (ToolCall) | `state-tool-{callId}-args` / `-result` | `state-tool-3f4a...-args` | |
| State nodes (ProcessingCall) | `state-proc-{callId}-input` / `-output` | `state-proc-3f4a1b2c-...-input` | Full callId to avoid collisions |
| Transition nodes (AgentCall) | `trans-agent-{callId}` | `trans-agent-3f4a1b2c-...` | |
| Transition nodes (LLMCall) | `trans-llm-{callId}` | `trans-llm-3f4a1b2c-...` | |
| Transition nodes (ToolCall) | `trans-tool-{callId}` | `trans-tool-3f4a1b2c-...` | |
| Transition nodes (ProcessingCall) | `trans-proc-{callId}` | `trans-proc-3f4a1b2c-...` | |
| Session | `session-{run_id}` | `session-run-abc123def456` | |
| Run | `run_id` itself | `run-abc123def456` | |
| Agent | `agent_id` string | `orchestrator` | |
| ThinkingCall | `{llmCallId}-thinking` | `3f4a1b2c-...-thinking` | |
| Synthesised ProcessingCall | `synth-pc-{agentCallId[:8]}` | `synth-pc-3f4a1b2c` | |
| Catalog Tool | `catalog:tool:{name}` | `catalog:tool:search_web` | |
| Catalog LLM | `catalog:model:{name}` | `catalog:model:claude-sonnet-4-5` | |
| Catalog Skill | `catalog:skill:{name}` | `catalog:skill:summarize` | |
| Catalog Processing | `catalog:processing:{name}` | `catalog:processing:context_assembly` | |

### Content Hash vs Node ID

The `State.contentHash` is a SHA-256 hex of the state content string. It is distinct from the node identity (`stateNodeId`):

- Same content in two different sessions → same `contentHash`, different `stateNodeId`.
- This enables **embedding reuse**: a vector index can deduplicate states by `contentHash` without conflating identities across traces.

### AgentCall Merge Key

Because a single `call_id` may be shared across events for the same agent call, the merge key in `call_nodes` is `_call_nodes_merge_key(call_id, local_name, agent_id)`:

- For `AgentCall`: `f"{call_id}::{agent_id}"` — disambiguates when the same `call_id` appears for different agents (edge case in some instrumentation patterns).
- For all other types: `call_id` itself.

---

*For the ontology schema that defines these node types and edge types, see [ontology.md](ontology.md). For the pipeline step wrappers that invoke `normalize_events` and `extract_graph`, see [steps.md](steps.md). For Neo4j push and query patterns, see [neo4j.md](neo4j.md).*
