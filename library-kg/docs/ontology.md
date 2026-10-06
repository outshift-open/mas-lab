# MAS Knowledge Graph Ontology Reference

**Document:** `mas-lab-internal/library-kg/docs/ontology.md`
**Scope:** Canonical definition of every node type, edge type, attribute, constraint, and ID-construction rule in the MAS Knowledge Graph ontology.

See also: [normalization.md](normalization.md) · [steps.md](steps.md) · [neo4j.md](neo4j.md)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Layer Overview](#2-layer-overview)
3. [Common Attributes](#3-common-attributes)
4. [Node ID Construction](#4-node-id-construction)
5. [Core Layer (L0)](#5-core-layer-l0)
   - 5.1 [Structural Catalog Nodes](#51-structural-catalog-nodes)
   - 5.2 [Execution Node Attribute Tables](#52-execution-node-attribute-tables)
   - 5.3 [Core Edges](#53-core-edges)
   - 5.4 [Core Constraints](#54-core-constraints)
   - 5.5 [Core Layer Examples](#55-core-layer-examples)
6. [Trajectory Layer (L2)](#6-trajectory-layer-l2)
   - 6.1 [Mealy Machine Semantics](#61-mealy-machine-semantics)
   - 6.2 [Trajectory Node Attribute Tables](#62-trajectory-node-attribute-tables)
   - 6.3 [Trajectory Edges](#63-trajectory-edges)
   - 6.4 [Trajectory Constraints](#64-trajectory-constraints)
   - 6.5 [Trajectory Examples](#65-trajectory-examples)
7. [Provenance Layer (L4)](#7-provenance-layer-l4)
   - 7.1 [ContextContribution Semantics](#71-contextcontribution-semantics)
   - 7.2 [Provenance Node Attributes](#72-provenance-node-attributes)
   - 7.3 [The σ DAG (derivedFrom Edges)](#73-the-σ-dag-derivedfrom-edges)
   - 7.4 [Provenance Constraints](#74-provenance-constraints)
   - 7.5 [Provenance Examples](#75-provenance-examples)
8. [Infrastructure Layer (L1)](#8-infrastructure-layer-l1)
   - 8.1 [Worker Node Attributes](#81-worker-node-attributes)
   - 8.2 [Infrastructure Edges and Constraints](#82-infrastructure-edges-and-constraints)
9. [Governance Layer (L5)](#9-governance-layer-l5)
   - 9.1 [Annotation-as-Governance Pattern](#91-annotation-as-governance-pattern)
   - 9.2 [CallAnnotation Attributes](#92-callannotation-attributes)
   - 9.3 [annotation_kind Values](#93-annotation_kind-values)
   - 9.4 [Governance Edges and Constraints](#94-governance-edges-and-constraints)
   - 9.5 [Governance Examples](#95-governance-examples)
10. [Global Constraints (G1–G8)](#10-global-constraints-g1g8)
11. [URN Scope Conventions](#11-urn-scope-conventions)
12. [Verification](#12-verification)

---

## 1. Overview

### What the ontology is

The MAS Knowledge Graph ontology defines the typed vocabulary used to represent
multi-agent system (MAS) execution traces as a property graph.  Every run of a
MAS produces a stream of raw events; the normalization pipeline (see
[normalization.md](normalization.md)) maps those events onto the node and edge
types defined here.  The resulting `kg.jsonld` document, or its Neo4j projection
(see [neo4j.md](neo4j.md)), is the authoritative record of what a system did,
why, and in what order.

### Where it lives

The ontology is implemented in `mas.library.kg.core.ontology`.  The SHACL shapes
that enforce it programmatically live alongside the normalization step.
`run_validate_kg` (see [steps.md](steps.md)) evaluates a materialized `kg.jsonld`
against a subset of these constraints at runtime; the remaining constraints (those
that require cross-document or cross-session context) must be verified externally.

### How it is used

The ontology serves three purposes:

| Purpose | How it helps |
|---------|-------------|
| **Normalization target** | The normalizer translates raw events into ontology-typed nodes and edges, ensuring a uniform schema across all MAS frameworks and runtimes. |
| **Query contract** | Downstream analysis tools (KG compare, RAG, annotation pipelines) rely on stable attribute names and edge types defined here. |
| **Compliance surface** | Governance tooling inspects `CallAnnotation` nodes, budget events, and policy edges whose structure is specified in L5. |

### Design goals

- **Layered**: each layer can be enabled or disabled independently.  A minimal
  deployment carries only L0 and L2; L1, L4, and L5 add overhead that is only
  worthwhile for specific observability or compliance use cases.
- **Stable IDs**: every node ID is deterministically derived from its content so
  that re-ingesting the same trace never creates duplicates (see §4).
- **Closed-world for catalog nodes, open-world for execution nodes**: catalog
  nodes (§5.1) must be declared before they can be referenced; execution nodes
  can reference catalog entries that arrive later in the stream, subject to G7.

---

## 2. Layer Overview

| Layer | Tag | Default | Event kinds |
|-------|-----|---------|-------------|
| Core | L0 | always on | `tool_call`, `llm_call`, `execution` (→ AgentCall), `mas_call`, `rag_query`, `memory_call`, `processing_call`, `skill_execution`, `network_call`, `workflow_transition` |
| Infrastructure | L1 | **off** | `infrastructure_info` (→ Worker) |
| Trajectory | L2 | **on** | `parallel_group`, `branch`, `routing`, `routing_result` |
| Provenance | L4 | **off** | `context_part_contributed` (→ ContextContribution) |
| Governance | L5 | **off** | `audit`, `policy_denial`, `policy_allow`, `budget_event`, `transformation_event`, `control_intervention`, `hitl_gate`, `governance_denied`, `governance_checked` |

**Why L2 is on by default:** State and Transition nodes encode the agent's
Mealy-machine execution path.  They are the primary unit of analysis for latency
attribution, loop detection, and trajectory comparison (§6.1).  Their storage
overhead is low relative to the analytical value they provide.

**Why L1, L4, L5 are off by default:** Worker nodes (L1) require process-level
instrumentation that not all runtimes expose.  ContextContribution nodes (L4) add
one node per LLM context slot, which can be thousands of nodes per session.
Governance nodes (L5) are only meaningful when a policy engine is wired into the
MAS.  All three layers can be enabled per-run by setting the corresponding feature
flag in the normalizer configuration.

---

## 3. Common Attributes

Every execution node (Session, MASCall, AgentCall, LLMCall, ToolCall, MemoryCall,
RAGQuery, ProcessingCall, SkillCall) carries the following attributes.  Catalog
nodes (Agent, Tool, LLM, etc.) do **not** carry these fields — they have their own
identity attributes described in §5.1.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `call_id` | `str` | yes | Unique identifier for this execution event. Forms the basis of most node IDs (see §4). |
| `parent_call_id` | `str \| null` | conditional | `call_id` of the immediately enclosing execution node. Null only on the root MASCall or a top-level AgentCall. Required when the node is nested (G3). |
| `agent_id` | `str` | yes | Logical identifier of the agent that produced this event. Must match an `Agent` catalog node's `agent_id` field. |
| `run_id` | `str` | yes | Identifier of the pipeline run. All nodes in a single run share the same `run_id`. |
| `session_id` | `str` | yes | Identifier of the user session. One session may contain multiple runs. Maps to the `Session` node's `session_id`. |
| `start_time` | `str (ISO 8601)` | yes | Wall-clock time when this execution began. |
| `end_time` | `str (ISO 8601)` | yes | Wall-clock time when this execution completed. |
| `duration` | `float` | yes | Elapsed milliseconds: `(end_time − start_time) × 1000`. Must be ≥ 0 (enforced by G2). |

### Derived fields added by `denormalize`

When a KG document is pushed to Neo4j, `denormalize` propagates three
session-scoped fields to every node and edge that do not already carry them:

| Field | Source |
|-------|--------|
| `sessionId` | Resolved from the `Session` node or any node's `run_id` |
| `appId` | Supplied as `app_name` parameter to `push_kg_to_neo4j` |
| `source` | Defaults to `"mas-lab"`; overridable per push call |

These fields are not part of the ontology proper but are required by the Neo4j
index strategy.  See [neo4j.md](neo4j.md) for details.

---

## 4. Node ID Construction

Node IDs must be stable across re-ingestion (G8).  Use the following patterns
exactly.  Any deviation will cause `MERGE` deduplication in Neo4j to fail and
duplicate nodes to accumulate.

| Node type | ID pattern | Example |
|-----------|-----------|---------|
| Session | `session:{session_id}` | `session:sess-abc-123` |
| AgentCall | `call:{call_id}` | `call:agt-7f3a` |
| LLMCall | `call:{call_id}` | `call:llm-9b12` |
| ToolCall | `call:{call_id}` | `call:tool-2c4d` |
| MASCall | `call:{call_id}` | `call:mas-0001` |
| MemoryCall | `call:{call_id}` | `call:mem-a9f2` |
| RAGQuery | `call:{call_id}` | `call:rag-6e1b` |
| ProcessingCall | `call:{call_id}` | `call:proc-3d7c` |
| SkillCall | `call:{call_id}` | `call:skill-5f8e` |
| State | `state:{agent_id}:{call_id}:{mealy_symbol}` | `state:planner:agt-7f3a:THINKING` |
| Transition | `transition:{from_state_id}:{to_state_id}` | `transition:state:planner:agt-7f3a:THINKING:state:planner:agt-7f3a:TOOL_USE` |
| ContextContribution | `contribution:{source_call_id}:{content_hash}` | `contribution:call:llm-9b12:a3f7c2d1` |
| CallAnnotation | `annotation:{annotation_id}` | `annotation:gov-0045` |
| Worker | `worker:{worker_id}` | `worker:pid-18342` |

### Catalog node IDs

Catalog nodes use a `spec:` prefix to distinguish them from execution nodes and
to match the interning scheme described in [kg-spec.md](kg-spec.md):

| Catalog node type | ID pattern | Example |
|-------------------|-----------|---------|
| Agent | `spec:agent:{agent_id}` | `spec:agent:planner` |
| MAS | `spec:mas:{mas_id}` | `spec:mas:support-pipeline` |
| Task | `spec:task:{task_id}` | `spec:task:ticket-classify` |
| LLM | `spec:llm:{model}` | `spec:llm:claude-3-5-sonnet` |
| Tool | `spec:tool:{tool_name}` | `spec:tool:search_kb` |
| Processing | `spec:processing:{processing_name}` | `spec:processing:chunk-and-embed` |
| Skill | `spec:skill:{skill_id}` | `spec:skill:summarise` |
| Memory | `spec:memory:{memory_id}` | `spec:memory:episodic-store` |
| Workflow | `spec:workflow:{workflow_id}` | `spec:workflow:triage-resolve` |
| DesignPattern | `spec:dp:{dp_id}` | `spec:dp:orchestrator-subagent` |

### Why all execution nodes share the `call:` prefix

A `call_id` is already unique across node types within a run.  Sharing the
`call:` prefix keeps ID construction simple and makes it possible to look up any
execution node by its `call_id` without knowing its type.

---

## 5. Core Layer (L0)

L0 is always active.  It defines the minimum viable knowledge graph: what the
system is made of (catalog nodes) and what actually executed (execution nodes).

---

### 5.1 Structural Catalog Nodes

Catalog nodes record design-time declarations.  They are not execution events and
do not carry the common attributes from §3.  The same catalog node is shared
across all runs of the same MAS version (interned once; see
[kg-spec.md](kg-spec.md)).

| Node type | Identity attribute | Description |
|-----------|--------------------|-------------|
| `Agent` | `agent_id` | A logical agent in the MAS.  One `Agent` node per role, not per invocation. |
| `MAS` | `mas_id` | The multi-agent system as a whole.  Typically one per deployment configuration. |
| `Task` | `task_id` | A declared task that the MAS is designed to accomplish. |
| `LLM` | `model` | A language model available for use.  E.g., `claude-3-5-sonnet`, `gpt-4o`. |
| `Tool` | `tool_name` | A callable tool registered in the system.  Referenced by every ToolCall via G7. |
| `Processing` | `processing_name` | A named data-processing step (chunking, embedding, tokenization, etc.). |
| `Skill` | `skill_id` | A reusable multi-step procedure that an agent may execute. |
| `Memory` | `memory_id` | A memory backend (vector store, episodic store, working memory, etc.). |
| `Workflow` | `workflow_id` | A declared workflow or pipeline that the MAS implements. |
| `DesignPattern` | `dp_id` | A recognized MAS design pattern (orchestrator-subagent, reflection, etc.). |

**Relationship to spec nodes:** When `merge_spec_into_kg` is called (see
[kg-spec.md](kg-spec.md)), it creates `AgentSpec`, `ToolSpec`, and `SkillSpec`
nodes with IDs matching the `spec:` patterns above.  These serve as the canonical
catalog nodes for conformance-edge wiring.

---

### 5.2 Execution Node Attribute Tables

#### Session

| Attribute | Type | Description |
|-----------|------|-------------|
| `session_id` | `str` | Stable session identifier.  Scopes all runs within a user conversation or task. |

#### MASCall

Carries all [common attributes](#3-common-attributes).  No additional attributes.
Represents the top-level invocation of the MAS for one user turn.

#### AgentCall

Carries all [common attributes](#3-common-attributes), plus:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `input` | `str \| dict` | yes | The input passed to this agent invocation. |
| `output` | `str \| dict` | yes | The output returned by this agent invocation. |
| `dp_id` | `str \| null` | no | Design pattern identifier. If set, must reference a `DesignPattern` catalog node. |
| `failure_reason` | `str \| null` | no | Human-readable description of why the invocation failed. Null on success. |
| `failure_category` | `str \| null` | no | Structured failure category.  Allowed values: `timeout`, `tool_error`, `llm_error`, `budget_exceeded`, `policy_denial`, `unknown`. |

#### LLMCall

Carries all [common attributes](#3-common-attributes), plus:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | `str` | yes | Model identifier, e.g. `claude-3-5-sonnet`.  Must match an `LLM` catalog node. |
| `prompt` | `str` | yes | Full prompt sent to the model, including system prompt and message history. |
| `completion` | `str` | yes | The model's response text. |
| `thinking` | `str \| null` | no | Extended thinking / chain-of-thought content returned by the model, when available. |
| `prompt_token_count` | `int` | yes | Tokens in the prompt. |
| `completion_token_count` | `int` | yes | Tokens in the completion. |
| `total_token_count` | `int` | yes | Sum of prompt and completion token counts. |
| `temperature` | `float \| null` | no | Sampling temperature used for this call. |
| `finish_reason` | `str` | yes | Reason the model stopped generating.  Typical values: `stop`, `length`, `tool_use`, `content_filter`. |

#### ToolCall

Carries all [common attributes](#3-common-attributes), plus:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_name` | `str` | yes | Name of the tool invoked.  Must match a `Tool` catalog node (G7). |
| `tool_arguments` | `dict` | yes | Arguments passed to the tool, as a JSON-serializable dict. |
| `tool_output` | `str \| dict` | yes | Return value from the tool. |
| `tool_category` | `str \| null` | no | Semantic category.  Suggested values: `retrieval`, `action`, `computation`, `communication`, `filesystem`, `external_api`. |
| `barrier_id` | `str \| null` | no | When set, this tool call is the synchronization point for a parallel group. References a `ParallelGroup.group_id`. |

#### MemoryCall

Carries all [common attributes](#3-common-attributes), plus:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `memory_type` | `str` | yes | Type of memory backend: `episodic`, `semantic`, `working`, `procedural`. |
| `memory_operation` | `str` | yes | Operation performed: `read`, `write`, `update`, `delete`, `search`. |
| `memory_key` | `str \| null` | no | Key used for read/write/update/delete operations on key-value stores. |
| `memory_query` | `str \| null` | no | Query string used for search operations. |
| `memory_output` | `str \| dict \| null` | no | Result of the memory operation. |
| `memory_result_count` | `int \| null` | no | Number of results returned by a search operation. |

#### RAGQuery

Carries all [common attributes](#3-common-attributes), plus:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `rag_query` | `str` | yes | The retrieval query issued. |
| `rag_result_count` | `int` | yes | Number of chunks or documents retrieved. |

#### ProcessingCall

Carries all [common attributes](#3-common-attributes), plus:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `processing_name` | `str` | yes | Name of the processing step.  Must match a `Processing` catalog node. |
| `processing_type` | `str` | yes | Category of processing: `chunking`, `embedding`, `tokenization`, `formatting`, `extraction`, `transformation`. |
| `processing_segments` | `int \| null` | no | Number of segments or chunks produced by the processing step. |
| `processing_tokens` | `int \| null` | no | Token count consumed or produced by the processing step. |

#### SkillCall

Carries all [common attributes](#3-common-attributes).  No additional ontology
attributes.  Skill-specific metadata is carried on the linked `Skill` catalog node
and on the child `AgentCall`, `LLMCall`, or `ToolCall` nodes produced during skill
execution.

---

### 5.3 Core Edges

| Source node type | Edge type | Target node type | Description |
|-----------------|-----------|-----------------|-------------|
| `Session` | `hasRun` | `MASCall` or `AgentCall` | Links a session to its top-level execution nodes. |
| `MASCall` | `hasCall` | `AgentCall` | A MAS-level invocation spawns one or more agent invocations. |
| `AgentCall` | `hasCall` | `LLMCall` | An agent invocation produces one or more LLM calls. |
| `AgentCall` | `hasCall` | `ToolCall` | An agent invocation produces one or more tool calls (direct, not via LLM). |
| `AgentCall` | `hasCall` | `MemoryCall` | An agent invocation reads or writes memory. |
| `AgentCall` | `hasCall` | `ProcessingCall` | An agent invocation triggers a processing step. |
| `AgentCall` | `hasCall` | `SkillCall` | An agent invocation executes a skill. |
| `LLMCall` | `hasCall` | `ToolCall` | A tool call originating from an LLM tool-use response. |
| `AgentCall` | `annotatedBy` | `CallAnnotation` | Links a governance or evaluation annotation to an agent call (L5). |
| `AgentCall` | `hasState` | `State` | Links an agent call to its Mealy-machine states (L2). |

**Cardinality guidance:**

- `Session → hasRun → MASCall`: one-to-many (one session, multiple turns).
- `AgentCall → hasCall → LLMCall`: typically one-to-many (a ReAct loop produces multiple LLM calls per agent call).
- `LLMCall → hasCall → ToolCall`: one-to-many (a single LLM response may request multiple tool calls in parallel).
- `AgentCall → hasState → State`: one-to-many (one state per Mealy symbol visited).

---

### 5.4 Core Constraints

| ID | Constraint | Rationale |
|----|-----------|-----------|
| C0-1 | Every execution node must carry `call_id`, `agent_id`, `session_id` (G1). | These three fields are the minimum required to reconstruct the call tree and scope queries by session. |
| C0-2 | `tool_name` on every `ToolCall` must correspond to an existing `Tool` catalog node (G7). | Prevents orphaned tool references that cannot be traced to a declared capability. |
| C0-3 | Every `LLMCall` within an `AgentCall` must satisfy `LLMCall.parent_call_id = AgentCall.call_id` (G5). | Ensures LLM calls are always correctly nested under their containing agent call. |
| C0-4 | `start_time ≤ end_time` on all execution nodes (G2). | Negative durations indicate instrumentation bugs. |

---

### 5.5 Core Layer Examples

**Minimal single-agent run (Python dict representation):**

```python
{
  "nodes": [
    {"id": "session:sess-001",      "node_type": "Session",   "session_id": "sess-001"},
    {"id": "call:agt-001",          "node_type": "AgentCall", "call_id": "agt-001",
     "agent_id": "resolver", "session_id": "sess-001", "run_id": "run-001",
     "start_time": "2025-01-15T10:00:00Z", "end_time": "2025-01-15T10:00:03Z",
     "duration": 3000.0,
     "input": "What is the refund policy?", "output": "Refunds are accepted within 30 days."},
    {"id": "call:llm-001",          "node_type": "LLMCall",   "call_id": "llm-001",
     "parent_call_id": "agt-001",   "agent_id": "resolver",   "session_id": "sess-001",
     "run_id": "run-001",
     "start_time": "2025-01-15T10:00:00.1Z", "end_time": "2025-01-15T10:00:02.9Z",
     "duration": 2800.0,
     "model": "claude-3-5-sonnet",
     "prompt": "You are a support agent...\nUser: What is the refund policy?",
     "completion": "Refunds are accepted within 30 days.",
     "prompt_token_count": 320, "completion_token_count": 18, "total_token_count": 338,
     "temperature": 0.2, "finish_reason": "stop"},
  ],
  "edges": [
    {"from_id": "session:sess-001", "to_id": "call:agt-001", "edge_type": "hasRun"},
    {"from_id": "call:agt-001",     "to_id": "call:llm-001", "edge_type": "hasCall"},
  ]
}
```

**ToolCall nested under LLMCall:**

```python
# LLMCall with finish_reason=tool_use spawns a ToolCall child
{"id": "call:llm-002", "node_type": "LLMCall", "call_id": "llm-002",
 "parent_call_id": "agt-001", "finish_reason": "tool_use", ...},
{"id": "call:tool-001", "node_type": "ToolCall", "call_id": "tool-001",
 "parent_call_id": "llm-002",
 "tool_name": "search_kb",
 "tool_arguments": {"query": "refund policy", "top_k": 5},
 "tool_output": ["Policy doc §4.2: 30-day returns...", "FAQ: refunds..."],
 "tool_category": "retrieval"},

# Edge: LLMCall → hasCall → ToolCall
{"from_id": "call:llm-002", "to_id": "call:tool-001", "edge_type": "hasCall"}
```

---

## 6. Trajectory Layer (L2)

L2 is enabled by default.  It records the agent's internal execution trajectory
as a Mealy finite-state machine, enabling step-level latency attribution, loop
detection, and structural comparison across runs.

---

### 6.1 Mealy Machine Semantics

A Mealy machine is a finite automaton where outputs (here: `mealy_symbol` labels)
are associated with transitions rather than states.  In the MAS KG:

- Each **State node** represents a snapshot of the agent at a specific phase of
  its `AgentCall`.  The `mealy_symbol` on a State node is the label of the
  transition that *led into* that state.
- Each **Transition node** records the arc between two consecutive states.  Its
  `mealy_symbol` is the observable event that caused the state change (e.g.,
  `TOOL_RESULT_RECEIVED`).
- The sequence of states within an `AgentCall` forms a path through the agent's
  decision graph, which is directly comparable across runs using structural
  similarity metrics.

**Standard mealy_symbol values (L2 vocabulary):**

| Symbol | Meaning |
|--------|---------|
| `INIT` | Initial state at the start of the AgentCall |
| `THINKING` | LLM is generating a response |
| `TOOL_USE` | LLM has emitted a tool-use request |
| `TOOL_RESULT_RECEIVED` | Tool output has been returned and appended to context |
| `REFLECTION` | Agent is evaluating whether to continue or stop |
| `ROUTING` | Agent is selecting a subagent or routing to a branch |
| `WAITING_PARALLEL` | Agent is waiting on parallel branches to complete |
| `PARALLEL_JOINED` | All parallel branches have completed |
| `DONE` | AgentCall has produced its final output |
| `ERROR` | AgentCall terminated due to an error |

Custom symbols are allowed.  Any string value is valid; define custom symbols in
the MAS configuration so that downstream tooling can interpret them.

---

### 6.2 Trajectory Node Attribute Tables

#### State

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `state_id` | `str` | yes | Stable ID for this state instance.  Derived from `agent_id`, `call_id`, and `mealy_symbol` (see §4). |
| `agent_id` | `str` | yes | Agent that this state belongs to. |
| `mealy_symbol` | `str` | yes | The transition label that produced this state. `INIT` for the first state in an AgentCall. |
| Common attributes | — | yes | All fields from §3. |

#### Transition

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `transition_id` | `str` | yes | Derived from `from_state_id` and `to_state_id` (see §4). |
| `from_state_id` | `str` | yes | ID of the state this transition departs from. |
| `to_state_id` | `str` | yes | ID of the state this transition leads to. |
| `mealy_symbol` | `str` | yes | The observable event label for this arc. |
| `timestamp` | `str (ISO 8601)` | yes | Wall-clock time at which this transition fired. |
| `call_id` | `str` | yes | `call_id` of the execution event (LLMCall, ToolCall, etc.) that triggered this transition. |

#### ParallelGroup

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `group_id` | `str` | yes | Unique identifier for this parallel execution group. |
| `branch_count` | `int` | yes | Total number of branches in the group.  All branches must complete before the group can join. |

#### Branch

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `branch_id` | `str` | yes | Unique identifier for this branch instance. |
| `group_id` | `str` | yes | `group_id` of the `ParallelGroup` this branch belongs to. |
| `branch_index` | `int` | yes | Zero-based index of this branch within the group.  Must be unique within the group and in `[0, branch_count − 1]`. |

---

### 6.3 Trajectory Edges

| Source | Edge type | Target | Description |
|--------|-----------|--------|-------------|
| `AgentCall` | `hasState` | `State` | An agent call owns all states visited during its execution. |
| `State` | `hasTransition` | `Transition` | A state can fire one or more transitions (usually one at a time). |
| `Transition` | `leadsTo` | `State` | The destination state of a transition. |
| `AgentCall` | `parallels` | `ParallelGroup` | An agent call spawns a parallel group. |
| `ParallelGroup` | `hasBranch` | `Branch` | A parallel group contains its branches. |

**Traversal pattern for the full trajectory of an AgentCall:**

```cypher
MATCH path = (ac:AgentCall {id: $call_id})
  -[:hasState]->  (s0:State  {mealy_symbol: "INIT"})
  -[:hasTransition*]->(:Transition)
  -[:leadsTo*]->(sN:State)
RETURN path
```

---

### 6.4 Trajectory Constraints

| ID | Constraint |
|----|-----------|
| C2-1 | State nodes must be reachable from their AgentCall via `hasState`. |
| C2-2 | `Transition.from_state_id` and `to_state_id` must reference existing State nodes. |
| C2-3 | `Branch.branch_index` values within a group must be unique and in `[0, branch_count − 1]`. |
| C2-4 | Every AgentCall must have at least one State node (the `INIT` state) (G4). |
| C2-5 | The path `INIT → ... → DONE|ERROR` must be acyclic within a single AgentCall. Cycles indicate loops in the agent's reasoning, which must be detected and flagged rather than silently represented. |

---

### 6.5 Trajectory Examples

**Two-step ReAct trajectory (INIT → THINKING → TOOL_USE → TOOL_RESULT_RECEIVED → THINKING → DONE):**

```python
# State nodes
{"id": "state:planner:agt-001:INIT",                  "node_type": "State",
 "mealy_symbol": "INIT",         "agent_id": "planner", "call_id": "agt-001", ...},
{"id": "state:planner:agt-001:THINKING",              "node_type": "State",
 "mealy_symbol": "THINKING",     "agent_id": "planner", "call_id": "agt-001", ...},
{"id": "state:planner:agt-001:TOOL_USE",              "node_type": "State",
 "mealy_symbol": "TOOL_USE",     "agent_id": "planner", "call_id": "agt-001", ...},
{"id": "state:planner:agt-001:TOOL_RESULT_RECEIVED",  "node_type": "State",
 "mealy_symbol": "TOOL_RESULT_RECEIVED", "agent_id": "planner", "call_id": "agt-001", ...},
{"id": "state:planner:agt-001:DONE",                  "node_type": "State",
 "mealy_symbol": "DONE",         "agent_id": "planner", "call_id": "agt-001", ...},

# Transition nodes
{"id": "transition:state:planner:agt-001:INIT:state:planner:agt-001:THINKING",
 "node_type": "Transition", "from_state_id": "state:planner:agt-001:INIT",
 "to_state_id": "state:planner:agt-001:THINKING",
 "mealy_symbol": "THINKING", "call_id": "llm-001", "timestamp": "2025-01-15T10:00:00.1Z"},
# ... remaining transitions follow the same pattern
```

**ParallelGroup with two branches:**

```python
{"id": "pg-001",    "node_type": "ParallelGroup", "group_id": "pg-001", "branch_count": 2},
{"id": "br-001",    "node_type": "Branch", "branch_id": "br-001", "group_id": "pg-001", "branch_index": 0},
{"id": "br-002",    "node_type": "Branch", "branch_id": "br-002", "group_id": "pg-001", "branch_index": 1},

{"from_id": "call:agt-001", "to_id": "pg-001",  "edge_type": "parallels"},
{"from_id": "pg-001",       "to_id": "br-001",  "edge_type": "hasBranch"},
{"from_id": "pg-001",       "to_id": "br-002",  "edge_type": "hasBranch"},
```

---

## 7. Provenance Layer (L4)

L4 is **off by default** and should be enabled only when per-token context
attribution is required (e.g., for RAG provenance audits or context budget
optimization).

---

### 7.1 ContextContribution Semantics

A `ContextContribution` node records one distinct piece of content that was
present in an LLM call's prompt context.  Each contribution is linked to:

- The `LLMCall` whose prompt contained it (via `hasContextPart`).
- The originating execution node that produced the content (via `source_call_id`).

This makes it possible to answer: "which prior tool results, memory reads, and
agent outputs contributed to the context that produced this LLM response?"

**Semantic types of context contributions:**

| `semantic_type` | Meaning |
|----------------|---------|
| `system_prompt` | Static system-level instructions |
| `user_message` | Direct user input |
| `tool_result` | Output from a prior ToolCall |
| `memory_retrieval` | Content retrieved from a MemoryCall |
| `rag_chunk` | A document chunk from a RAGQuery |
| `agent_output` | Output from a prior AgentCall (e.g., in orchestrator patterns) |
| `assistant_message` | Prior model completion included in the context window |

---

### 7.2 Provenance Node Attributes

#### ContextContribution

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_call_id` | `str` | yes | `call_id` of the execution node that produced this content. Must reference an existing LLMCall (G6). |
| `semantic_type` | `str` | yes | Category of the contribution (see table above). |
| `content_hash` | `str` | yes | Stable SHA-256 (or similar) hash of the content.  Used to construct the node ID and to detect identical contributions across calls. |
| `tokens` | `int` | yes | Number of tokens this contribution occupies in the prompt context. |

---

### 7.3 The σ DAG (derivedFrom Edges)

Beyond the flat `hasContextPart` edges, L4 supports a `derivedFrom` edge that
connects one `ContextContribution` to another when the content of one is derived
from (summarized from, extracted from, or transformed from) another.  The
resulting directed acyclic graph (the σ DAG, σ for "sources") enables multi-hop
provenance queries:

```
LLMCall:llm-010
  └─hasContextPart─► contribution:llm-010:a3f7  (semantic_type=rag_chunk)
                          └─derivedFrom─► contribution:llm-005:9c2a  (semantic_type=tool_result)
                                              └─derivedFrom─► contribution:llm-001:4b8e  (semantic_type=user_message)
```

**σ DAG edges:**

| Source | Edge type | Target | Description |
|--------|-----------|--------|-------------|
| `LLMCall` | `hasContextPart` | `ContextContribution` | Primary edge; links a prompt to one of its context slots. |
| `ContextContribution` | `derivedFrom` | `ContextContribution` | Provenance lineage; the source contribution is an ancestor of the target. |

---

### 7.4 Provenance Constraints

| ID | Constraint |
|----|-----------|
| C4-1 | `ContextContribution.source_call_id` must reference an existing LLMCall node in the same trace (G6). |
| C4-2 | `content_hash` must be stable: the same content must always produce the same hash, regardless of when the node is ingested. |
| C4-3 | The σ DAG (the subgraph formed by `derivedFrom` edges) must be acyclic. |
| C4-4 | `tokens` must be ≥ 1. A zero-token contribution is nonsensical and indicates a normalization error. |

---

### 7.5 Provenance Examples

**RAG chunk contributing to an LLM call:**

```python
# ContextContribution for a retrieved chunk
{"id": "contribution:call:llm-009:a3f7c2d1",
 "node_type": "ContextContribution",
 "source_call_id": "call:llm-009",   # the LLMCall that contains this in its prompt
 "semantic_type": "rag_chunk",
 "content_hash": "a3f7c2d1",
 "tokens": 142},

# Edge: LLMCall → hasContextPart → ContextContribution
{"from_id": "call:llm-009", "to_id": "contribution:call:llm-009:a3f7c2d1",
 "edge_type": "hasContextPart"}
```

**Query: which tool results contributed to LLM call `llm-020`?**

```cypher
MATCH (llm:LLMCall {id: "call:llm-020"})
  -[:hasContextPart]-> (cc:ContextContribution {semantic_type: "tool_result"})
RETURN cc.source_call_id, cc.tokens
ORDER BY cc.tokens DESC
```

---

## 8. Infrastructure Layer (L1)

L1 is **off by default**.  Enable it when process-level worker attribution is
required for debugging crashes, tracking resource usage per worker process, or
auditing durable-backend persistence.

---

### 8.1 Worker Node Attributes

#### Worker

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `worker_id` | `str` | yes | Stable identifier for this worker.  Typically derived from hostname and PID: `{hostname}-{pid}`. |
| `worker_pid` | `int` | yes | Operating system process ID of the worker at the time the AgentCall was executed. |
| `durable_backend` | `str \| null` | no | Name or URI of the durable storage backend this worker is attached to (e.g., a Redis URI for checkpointing). |

---

### 8.2 Infrastructure Edges and Constraints

| Source | Edge type | Target | Description |
|--------|-----------|--------|-------------|
| `Worker` | `hosts` | `AgentCall` | Records which worker process executed a given AgentCall. |

| ID | Constraint |
|----|-----------|
| C1-1 | Infrastructure is optional.  Absence of a `Worker` node does not invalidate a KG document. |
| C1-2 | Each `AgentCall` may be linked to **at most one** `Worker` node.  Multiple worker links on a single call indicate a normalization error. |

**Example:**

```python
{"id": "worker:worker-node42-18342", "node_type": "Worker",
 "worker_id": "worker-node42-18342", "worker_pid": 18342,
 "durable_backend": "redis://redis-host:6379/0"},

{"from_id": "worker:worker-node42-18342", "to_id": "call:agt-001", "edge_type": "hosts"}
```

---

## 9. Governance Layer (L5)

L5 is **off by default**.  Enable it when policy enforcement, budget tracking, or
human-in-the-loop (HITL) gate records must be captured in the KG.

---

### 9.1 Annotation-as-Governance Pattern

Rather than adding governance attributes directly to execution nodes (which would
couple the core schema to policy logic), L5 uses a separate `CallAnnotation` node
attached via an `annotatedBy` edge.  This pattern has three benefits:

1. **Separation of concerns**: governance records can be written by a sidecar
   policy engine without mutating the primary execution record.
2. **Auditability**: the annotation node is independently queryable and can be
   indexed separately from the execution trace.
3. **Extensibility**: new `annotation_kind` values can be added without schema
   migration.

---

### 9.2 CallAnnotation Attributes

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `annotation_id` | `str` | yes | Unique identifier.  Forms the node ID as `annotation:{annotation_id}`. |
| `annotation_kind` | `str` | yes | Semantic type of this annotation (see §9.3). |
| `source_agent_id` | `str \| null` | no | `agent_id` of the agent or component that created this annotation (e.g., the policy engine). |
| `target_agent_id` | `str \| null` | no | `agent_id` of the agent that this annotation is about (typically the same as the `AgentCall.agent_id`). |

---

### 9.3 annotation_kind Values

The following `annotation_kind` values correspond to L5 event kinds:

| `annotation_kind` | Source event kind | Description |
|-------------------|------------------|-------------|
| `audit` | `audit` | A general audit record noting that a call was examined by a policy or monitoring component. |
| `policy_denial` | `policy_denial` | The call was blocked by a policy rule before execution could complete. |
| `policy_allow` | `policy_allow` | The call was explicitly allowed by a policy rule (as distinct from default pass-through). |
| `budget_event` | `budget_event` | A token or cost budget threshold was hit during this call. |
| `transformation_event` | `transformation_event` | Input or output content was transformed (redacted, anonymized, rewritten) by a governance component. |
| `control_intervention` | `control_intervention` | A control plane component (circuit breaker, rate limiter, etc.) intervened in this call. |
| `hitl_gate` | `hitl_gate` | A human-in-the-loop gate was triggered.  Execution may have been paused pending human review. |
| `governance_denied` | `governance_denied` | A higher-level governance check denied the call, distinct from a policy_denial at the rule level. |
| `governance_checked` | `governance_checked` | A governance check was performed and the call was permitted to proceed. |

---

### 9.4 Governance Edges and Constraints

| Source | Edge type | Target | Description |
|--------|-----------|--------|-------------|
| `AgentCall` | `annotatedBy` | `CallAnnotation` | Links an agent call to its governance annotation record. One AgentCall may have multiple CallAnnotation nodes (e.g., both an `audit` and a `policy_allow`). |

| ID | Constraint |
|----|-----------|
| C5-1 | An `AgentCall` may have zero or more `CallAnnotation` nodes.  The absence of annotations is not an error. |
| C5-2 | When `annotation_kind = policy_denial`, the associated `AgentCall.failure_category` should be set to `policy_denial` for consistency. |
| C5-3 | `annotation_id` must be unique across the trace. |

---

### 9.5 Governance Examples

**Policy denial annotation:**

```python
{"id": "annotation:gov-0045", "node_type": "CallAnnotation",
 "annotation_id": "gov-0045",
 "annotation_kind": "policy_denial",
 "source_agent_id": "policy-engine",
 "target_agent_id": "resolver"},

{"from_id": "call:agt-007", "to_id": "annotation:gov-0045", "edge_type": "annotatedBy"}
```

**HITL gate with policy_allow on resume:**

```python
# Gate fires — execution paused
{"id": "annotation:hitl-001", "node_type": "CallAnnotation",
 "annotation_id": "hitl-001", "annotation_kind": "hitl_gate",
 "source_agent_id": "hitl-controller", "target_agent_id": "executor"},

# Human approves — execution resumes with allow annotation
{"id": "annotation:gov-002", "node_type": "CallAnnotation",
 "annotation_id": "gov-002", "annotation_kind": "policy_allow",
 "source_agent_id": "human-reviewer-jsmith", "target_agent_id": "executor"},

# Both annotations are linked to the same AgentCall
{"from_id": "call:agt-012", "to_id": "annotation:hitl-001", "edge_type": "annotatedBy"},
{"from_id": "call:agt-012", "to_id": "annotation:gov-002",  "edge_type": "annotatedBy"},
```

**Query: all calls that were denied by policy in a session:**

```cypher
MATCH (ac:AgentCall:KGNode {sessionId: $session_id})
  -[:annotatedBy]-> (ann:CallAnnotation {annotation_kind: "policy_denial"})
RETURN ac.id, ac.agent_id, ann.source_agent_id
```

---

## 10. Global Constraints (G1–G8)

These constraints apply across all layers.  `run_validate_kg` checks G1–G7
structurally.  G8 (ID stability) must be verified by comparing re-ingested traces
against the database.

| ID | Constraint | Checked by | Why it matters |
|----|-----------|-----------|---------------|
| G1 | Every execution node must carry `call_id`, `agent_id`, and `session_id`. | `run_validate_kg` | These three fields are the minimum required to reconstruct the call tree, scope queries by session, and link execution records back to their originating agent. A node missing any of them cannot be reliably indexed or queried. |
| G2 | `start_time ≤ end_time` (equivalently, `duration ≥ 0`) on all execution nodes. | `run_validate_kg` | Negative durations indicate clock skew or instrumentation errors.  They corrupt latency metrics and can cause infinite loops in timeline reconstruction. |
| G3 | If `parent_call_id` is set, the referenced `call_id` must exist in the same trace. | `run_validate_kg` | Dangling parent references leave subtrees disconnected from the call root.  They prevent traversal of the full call hierarchy and can silently produce incomplete analysis results. |
| G4 | Every `AgentCall` must have at least one `State` node (the `INIT` state) when L2 is enabled. | `run_validate_kg` | An AgentCall without a trajectory record cannot be used for step-level analysis, loop detection, or structural comparison.  It also indicates that the normalizer's L2 event was dropped. |
| G5 | `LLMCall.parent_call_id` must equal its containing `AgentCall.call_id`. | `run_validate_kg` | LLM calls are always the direct children of an AgentCall, never children of other LLMCalls or ToolCalls.  Violations indicate mis-parented spans from the instrumentation layer. |
| G6 | `ContextContribution.source_call_id` must reference an existing LLMCall node in the same trace. | `run_validate_kg` | A ContextContribution without a resolvable source cannot be used for provenance attribution and may indicate a dropped or out-of-order event. |
| G7 | Every `ToolCall.tool_name` must appear as a `Tool` catalog node. | `run_validate_kg` | Undeclared tool usage cannot be linked to its spec, preventing capability coverage analysis, I/O schema validation, and conformance checking. |
| G8 | Node IDs must be stable across re-ingestion of the same trace. | External comparison | Non-stable IDs cause `MERGE` in Neo4j to create duplicate nodes on re-ingestion.  They also break cross-run comparisons that rely on ID equality to identify the same logical node. |

### G8 implementation guidance

G8 is satisfied automatically when ID construction follows §4 exactly.  The most
common causes of G8 violations:

- Using a random UUID as the `call_id` when the underlying event already carries a
  stable trace ID (e.g., an OTel span ID).  Always prefer the trace-originating ID.
- Including a wall-clock timestamp in a node ID.  Timestamps are not stable if the
  normalizer re-processes a trace with a slightly different `end_time` due to
  rounding.
- Using Python's `id()` or memory address of an object.  These are process-local
  and not reproducible.

---

## 11. URN Scope Conventions

When the KG is serialized as RDF (e.g., for SPARQL queries or interoperability
with external knowledge graphs), node IDs are expanded into URNs using the
following scope hierarchy:

| Scope | URN prefix | Example |
|-------|-----------|---------|
| Global | `urn:maskg:` | Reserved for cross-organization interoperability. Not used in standard deployments. |
| Organization | `urn:maskg:{org_id}:` | `urn:maskg:cisco:` — scopes the graph to a single organization. |
| MAS | `urn:maskg:{org_id}:{mas_id}:` | `urn:maskg:cisco:support-pipeline:` — scopes to a specific MAS deployment. |
| Session | `urn:maskg:{org_id}:{mas_id}:{session_id}:` | `urn:maskg:cisco:support-pipeline:sess-001:` — scopes to a single session. |

**Expansion rules:**

- Catalog node IDs (prefixed `spec:`) expand under the MAS scope, since they are
  shared across sessions: `spec:agent:planner` → `urn:maskg:cisco:support-pipeline:spec:agent:planner`.
- Execution node IDs (prefixed `call:`, `state:`, etc.) expand under the session
  scope: `call:agt-001` → `urn:maskg:cisco:support-pipeline:sess-001:call:agt-001`.
- Worker node IDs expand under the organization scope, since a worker process may
  host calls from multiple sessions: `worker:pid-18342` → `urn:maskg:cisco:worker:pid-18342`.

**In practice:** for Neo4j-only deployments (the standard case), URN expansion is
not required.  The short-form IDs from §4 are used directly as node `id`
properties.  URN expansion is only needed when the graph is exported for RDF
federation or linked-data publication.

**Namespace declaration for Turtle serialization:**

```turtle
@prefix maskg:    <urn:maskg:> .
@prefix mas-org:  <urn:maskg:cisco:> .
@prefix mas-sys:  <urn:maskg:cisco:support-pipeline:> .
@prefix mas-sess: <urn:maskg:cisco:support-pipeline:sess-001:> .
```

---

## 12. Verification

### What `run_validate_kg` checks automatically

`run_validate_kg` (see [steps.md](steps.md)) performs structural validation of a
materialized KG document.  It checks:

| Check | Global constraint enforced |
|-------|---------------------------|
| Every execution node carries `call_id`, `agent_id`, `session_id` | G1 |
| `start_time ≤ end_time` on all execution nodes | G2 |
| `parent_call_id` references resolve within the same trace | G3 |
| Every `AgentCall` has at least one `State` node (when L2 is present) | G4 |
| `LLMCall.parent_call_id = AgentCall.call_id` for all LLM calls | G5 |
| `ContextContribution.source_call_id` resolves to a `LLMCall` in the trace | G6 |
| `ToolCall.tool_name` matches a `Tool` catalog node | G7 |
| Schema-level attribute type checks (e.g., `duration` is float ≥ 0) | — |
| Required attributes are present on each node type | — |
| No duplicate node IDs within a document | — |

`run_validate_kg` returns a report dict with keys `valid` (bool), `errors` (list
of constraint violations), and `warnings` (list of non-fatal schema deviations).

### What must be checked externally

The following checks require cross-document or cross-session context that
`run_validate_kg` cannot access:

| Check | Reason it is external | Recommended approach |
|-------|-----------------------|---------------------|
| G8: Node ID stability across re-ingestion | Requires comparing a new trace against previously stored nodes in Neo4j. | Run `run_compare_kg` (see [steps.md](steps.md)) between the re-ingested KG and the stored KG for the same `session_id`. Any node present in only one version with a matching logical key is a G8 violation. |
| Catalog node completeness | A `Tool` catalog node may not be present if it was declared in a different KG document than the one being validated. | Call `merge_spec_into_kg` with the current `mas_spec` before validation so that catalog nodes are always present in the same document. |
| Cross-run trajectory consistency | Whether the same agent follows a consistent state machine across runs is a semantic question, not a structural one. | Use `run_compare_kg` across multiple KG documents for the same MAS configuration to detect trajectory drift. |
| σ DAG acyclicity (C4-3) | Cycle detection over the `derivedFrom` subgraph requires full graph traversal, which `run_validate_kg` only partially performs. | Run a dedicated Cypher query after pushing to Neo4j: `MATCH path = (c:ContextContribution)-[:derivedFrom*]->(c) RETURN path LIMIT 1` — any result indicates a cycle. |

### Running validation

```python
from mas.library.kg.steps import run_validate_kg

report = run_validate_kg("runs/001/kg.jsonld")

if not report["valid"]:
    for error in report["errors"]:
        print(f"[ERROR] {error['constraint']} — {error['message']}")
        print(f"        node: {error.get('node_id')}")
```

For continuous validation in a pipeline, wire `run_validate_kg` as a step
immediately after `run_normalize` and fail the pipeline on any `valid=False`
report before proceeding to annotation or Neo4j push steps.
