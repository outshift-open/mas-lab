# KG Spec Injection Module Reference

**Module:** `mas.library.kg.core.spec`
**Public API:** `from mas.library.kg import build_spec_nodes, merge_spec_into_kg`

---

## Table of Contents

1. [Conceptual Overview](#conceptual-overview)
2. [The `mas_spec` Dictionary Shape](#the-mas_spec-dictionary-shape)
3. [`build_spec_nodes`](#build_spec_nodes)
4. [`merge_spec_into_kg`](#merge_spec_into_kg)
5. [ASCII Diagram: Runtime Nodes Linked to Spec Sub-Graph](#ascii-diagram)
6. [Stable IDs](#stable-ids)
7. [Extending the Spec](#extending-the-spec)

---

## Conceptual Overview

### Design-time vs Runtime

A knowledge graph (KG) document produced by a MAS run carries two distinct layers
of information:

| Layer | Produced when | Contains |
|-------|--------------|----------|
| **Runtime** | During agent execution | `LLMCall`, `AgentCall`, `ToolCall`, `Observation`, `Message`, … nodes that record what actually happened |
| **Spec (design-time)** | Before / during system setup | `IntentSpec`, `AgentSpec`, `ToolSpec`, `SkillSpec` nodes that record what was *intended* |

The spec injection module bridges these layers by materialising the design-time
declarations as first-class KG nodes and then linking them to the matching
runtime nodes via *conformance edges*.

### Spec Sub-Graph as Shared Procedural Memory

The spec sub-graph acts as the system's procedural memory: it encodes the
blueprint that every run of a given MAS configuration is expected to follow.
Because the same `mas_spec` dict produces the same node IDs (see
[Stable IDs](#stable-ids)), the sub-graph is **interned once** per unique
specification version and reused across all runs that share that version.

This means:
- A vector index built over `AgentSpec` / `ToolSpec` nodes survives KG
  regeneration and does not need to be rebuilt when only runtime data changes.
- Cross-run comparisons can be done with simple ID lookups rather than
  fuzzy text matching.
- A single spec sub-graph can be stored in a shared collection and referenced
  by many per-run KG documents simultaneously.

### Why Intern Once Across Runs

If spec nodes were duplicated per run, the embedding index would grow linearly
with the number of runs even when the system design never changed.  Interning
means the spec sub-graph is inserted only on the first run (or when the spec
version changes), and subsequent runs attach runtime nodes to the already-
existing spec nodes.

### What Conformance Edges Enable

The `instanceOf` and `invokes` edges added by `merge_spec_into_kg` enable:

- **Compliance checking** – walk from a runtime call to its spec and verify
  that the inputs and outputs match the declared schemas.
- **Root-cause analysis** – when a ToolCall fails, traverse `invokes` to the
  `ToolSpec` to retrieve the expected I/O contract without re-parsing source
  code.
- **Capability coverage** – count which `AgentSpec.capabilities` were actually
  exercised across a set of runs.
- **Semantic search** – query "which agents can handle X?" by embedding
  `AgentSpec._text` fields instead of mining raw call logs.

---

## The `mas_spec` Dictionary Shape

All top-level keys are optional.  The module gracefully skips any section whose
key is absent.

```python
mas_spec = {
    # -----------------------------------------------------------------------
    # version (str, optional)
    #   An explicit version tag, e.g. "v1.2.0" or a git SHA.
    #   When omitted, the module computes sha256(repr(mas_spec))[:12].
    # -----------------------------------------------------------------------
    "version": "v1.0.0",

    # -----------------------------------------------------------------------
    # intent / goal (str, optional)
    #   Human-readable statement of the overall system purpose.
    #   Both keys are accepted; "intent" takes precedence over "goal".
    # -----------------------------------------------------------------------
    "intent": "Resolve customer support tickets using a two-agent pipeline.",

    # -----------------------------------------------------------------------
    # agents (list[dict], optional)
    #   Each entry describes one logical agent in the MAS.
    # -----------------------------------------------------------------------
    "agents": [
        {
            "id": "triage",               # str, required within entry
            "role": "Triage Agent",       # str, human label
            "intent": "Classify incoming tickets and route to the right specialist.",
            "capabilities": [             # list[str]
                "intent_classification",
                "priority_scoring",
            ],
            "skills": ["skill:summarise"],  # list of skill IDs (matched to SkillSpec)
            "tools": ["tool:search_kb"],    # list of tool IDs (matched to ToolSpec)
        },
        {
            "id": "resolver",
            "role": "Resolver Agent",
            "intent": "Generate a resolution for classified tickets.",
            "capabilities": ["answer_generation", "policy_lookup"],
            "skills": [],
            "tools": ["tool:search_kb", "tool:submit_resolution"],
        },
    ],

    # -----------------------------------------------------------------------
    # tools (list[dict], optional)
    #   Each entry describes one callable tool available in the system.
    # -----------------------------------------------------------------------
    "tools": [
        {
            "id": "search_kb",            # str, required within entry
            "in_schema": {                # dict, JSON-Schema fragment
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            "out_schema": {               # dict, JSON-Schema fragment
                "type": "array",
                "items": {"type": "string"},
            },
        },
        {
            "id": "submit_resolution",
            "in_schema": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "resolution": {"type": "string"},
                },
                "required": ["ticket_id", "resolution"],
            },
            "out_schema": {"type": "object", "properties": {"status": {"type": "string"}}},
        },
    ],

    # -----------------------------------------------------------------------
    # skills (list[dict], optional)
    #   Reusable multi-step procedures an agent may execute.
    # -----------------------------------------------------------------------
    "skills": [
        {
            "id": "summarise",            # str, required within entry
            "requires": ["text_input"],   # list[str], preconditions
            "concludes": "summary_output", # str, postcondition
        },
    ],
}
```

---

## `build_spec_nodes`

### Signature

```python
def build_spec_nodes(mas_spec: dict) -> tuple[list[dict], list[dict]]:
    ...
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `mas_spec` | `dict` | Design-time specification (see shape above). All keys optional. |

### Return Value

Returns a 2-tuple `(nodes, edges)`.

**`nodes`** – a flat list of node dicts.  Each node carries at minimum:

| Field | Type | Present on |
|-------|------|-----------|
| `id` | `str` | All nodes |
| `node_type` | `str` | All nodes |
| `version` | `str` | All nodes |
| `content` | `str` | All nodes |
| `_text` | `str` | All nodes (same as `content`, used for embedding) |
| `intent` | `str` | `IntentSpec`, `AgentSpec` |
| `role` | `str` | `AgentSpec` |
| `capabilities` | `list[str]` | `AgentSpec` |
| `skills` | `list[str]` | `AgentSpec` |
| `in_schema` | `dict` | `ToolSpec` |
| `out_schema` | `dict` | `ToolSpec` |
| `requires` | `list[str]` | `SkillSpec` |
| `concludes` | `str` | `SkillSpec` |

**`edges`** – a flat list of edge dicts, each with:

| Field | Type | Description |
|-------|------|-------------|
| `src` | `str` | Source node ID |
| `dst` | `str` | Destination node ID |
| `rel` | `str` | Relationship label |

Edge relationship labels produced by this function:

| `rel` | Direction | Meaning |
|-------|-----------|---------|
| `declaresSkill` | `AgentSpec` → `SkillSpec` | Agent declares it can execute the skill |
| `mayInvoke` | `AgentSpec` → `ToolSpec` | Agent declares it may call the tool |

### Example Output JSON

Given the `mas_spec` shown in the shape section (abbreviated), the call:

```python
nodes, edges = build_spec_nodes(mas_spec)
```

produces nodes like:

```json
[
  {
    "id": "spec:intent:mas",
    "node_type": "IntentSpec",
    "version": "v1.0.0",
    "content": "Resolve customer support tickets using a two-agent pipeline.",
    "_text": "Resolve customer support tickets using a two-agent pipeline."
  },
  {
    "id": "spec:agent:triage",
    "node_type": "AgentSpec",
    "version": "v1.0.0",
    "role": "Triage Agent",
    "intent": "Classify incoming tickets and route to the right specialist.",
    "capabilities": ["intent_classification", "priority_scoring"],
    "skills": ["skill:summarise"],
    "content": "AgentSpec triage | role=Triage Agent | intent=Classify incoming tickets and route to the right specialist. | capabilities=['intent_classification', 'priority_scoring']",
    "_text": "AgentSpec triage | role=Triage Agent | intent=Classify incoming tickets and route to the right specialist. | capabilities=['intent_classification', 'priority_scoring']"
  },
  {
    "id": "spec:agent:resolver",
    "node_type": "AgentSpec",
    "version": "v1.0.0",
    "role": "Resolver Agent",
    "intent": "Generate a resolution for classified tickets.",
    "capabilities": ["answer_generation", "policy_lookup"],
    "skills": [],
    "content": "AgentSpec resolver | role=Resolver Agent | intent=Generate a resolution for classified tickets. | capabilities=['answer_generation', 'policy_lookup']",
    "_text": "AgentSpec resolver | role=Resolver Agent | intent=Generate a resolution for classified tickets. | capabilities=['answer_generation', 'policy_lookup']"
  },
  {
    "id": "spec:tool:search_kb",
    "node_type": "ToolSpec",
    "version": "v1.0.0",
    "in_schema": {
      "type": "object",
      "properties": {
        "query": {"type": "string"},
        "top_k": {"type": "integer", "default": 5}
      },
      "required": ["query"]
    },
    "out_schema": {
      "type": "array",
      "items": {"type": "string"}
    },
    "content": "ToolSpec search_kb | in=object | out=array",
    "_text": "ToolSpec search_kb | in=object | out=array"
  },
  {
    "id": "spec:tool:submit_resolution",
    "node_type": "ToolSpec",
    "version": "v1.0.0",
    "in_schema": {
      "type": "object",
      "properties": {
        "ticket_id": {"type": "string"},
        "resolution": {"type": "string"}
      },
      "required": ["ticket_id", "resolution"]
    },
    "out_schema": {"type": "object", "properties": {"status": {"type": "string"}}},
    "content": "ToolSpec submit_resolution | in=object | out=object",
    "_text": "ToolSpec submit_resolution | in=object | out=object"
  },
  {
    "id": "spec:skill:summarise",
    "node_type": "SkillSpec",
    "version": "v1.0.0",
    "requires": ["text_input"],
    "concludes": "summary_output",
    "content": "SkillSpec summarise | requires=['text_input'] | concludes=summary_output",
    "_text": "SkillSpec summarise | requires=['text_input'] | concludes=summary_output"
  }
]
```

and edges like:

```json
[
  {
    "src": "spec:agent:triage",
    "dst": "spec:skill:summarise",
    "rel": "declaresSkill"
  },
  {
    "src": "spec:agent:triage",
    "dst": "spec:tool:search_kb",
    "rel": "mayInvoke"
  },
  {
    "src": "spec:agent:resolver",
    "dst": "spec:tool:search_kb",
    "rel": "mayInvoke"
  },
  {
    "src": "spec:agent:resolver",
    "dst": "spec:tool:submit_resolution",
    "rel": "mayInvoke"
  }
]
```

### Example 1 — Minimal spec (intent only)

```python
from mas.library.kg import build_spec_nodes

spec = {"intent": "Summarise a document and return key points."}
nodes, edges = build_spec_nodes(spec)

# nodes contains exactly one entry: the IntentSpec node.
# edges is an empty list.
assert len(nodes) == 1
assert nodes[0]["node_type"] == "IntentSpec"
assert nodes[0]["id"] == "spec:intent:mas"
# version is auto-generated from sha256(repr(spec))[:12]
assert len(nodes[0]["version"]) == 12
assert edges == []
```

### Example 2 — Two agents sharing a tool; no explicit version

```python
from mas.library.kg import build_spec_nodes

spec = {
    "agents": [
        {
            "id": "planner",
            "role": "Planning Agent",
            "intent": "Decompose the user task into sub-tasks.",
            "capabilities": ["task_decomposition"],
            "skills": [],
            "tools": ["tool:web_search"],
        },
        {
            "id": "executor",
            "role": "Execution Agent",
            "intent": "Execute sub-tasks produced by the planner.",
            "capabilities": ["code_execution"],
            "skills": [],
            "tools": ["tool:web_search", "tool:code_runner"],
        },
    ],
    "tools": [
        {"id": "web_search",  "in_schema": {"type": "object"}, "out_schema": {"type": "string"}},
        {"id": "code_runner", "in_schema": {"type": "object"}, "out_schema": {"type": "object"}},
    ],
}

nodes, edges = build_spec_nodes(spec)

# 2 AgentSpec + 2 ToolSpec = 4 nodes (no IntentSpec since intent key absent)
assert len(nodes) == 4

# Both agents declare mayInvoke for web_search; executor also declares code_runner
rels = [(e["src"], e["rel"], e["dst"]) for e in edges]
assert ("spec:agent:planner",  "mayInvoke", "spec:tool:web_search")  in rels
assert ("spec:agent:executor", "mayInvoke", "spec:tool:web_search")  in rels
assert ("spec:agent:executor", "mayInvoke", "spec:tool:code_runner") in rels
assert len(edges) == 3
```

---

## `merge_spec_into_kg`

### Signature

```python
def merge_spec_into_kg(kg_doc: dict, mas_spec: dict) -> dict:
    ...
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `kg_doc` | `dict` | An existing KG document (modified **in place**). Must have `"nodes"`, `"edges"`, and `"meta"` keys at the top level. |
| `mas_spec` | `dict` | Design-time specification (same shape as for `build_spec_nodes`). |

### Return Value

Returns the same `kg_doc` dict (modified in place).  The caller may ignore the
return value when mutating in-place is sufficient.

### Side Effects

1. Calls `build_spec_nodes(mas_spec)` internally.
2. **Interns** spec nodes: each spec node is appended to `kg_doc["nodes"]` only
   if no node with the same `id` already exists.  Existing runtime nodes are
   never overwritten.
3. **Interns** spec edges similarly.
4. Adds **conformance edges** (see below).
5. Sets `kg_doc["meta"]["spec_injected"] = True`.
6. Sets `kg_doc["meta"]["spec_node_count"]` to the number of unique spec nodes
   now present in `kg_doc["nodes"]`.

### Conformance Edge Rules

After interning spec nodes, the function scans every node in `kg_doc["nodes"]`
(including pre-existing runtime nodes) and creates conformance edges:

| Runtime node type | Matched field(s) | Edge added | To |
|-------------------|-----------------|-----------|-----|
| `AgentCall`, `LLMCall` | `agentId` or `agent_id` | `instanceOf` | `spec:agent:{id}` |
| `ToolCall` | `toolId`, `tool_id`, `toolName`, or `tool_name` | `invokes` | `spec:tool:{id}` |

Conformance edges are also interned: a given `(src, rel, dst)` triple is never
duplicated even if `merge_spec_into_kg` is called multiple times on the same
document.

If no matching spec node exists for a given runtime node, **no edge is added
and no error is raised** — the runtime node simply has no conformance link.

### Example 1 — Basic merge with a single AgentCall and ToolCall

```python
from mas.library.kg import merge_spec_into_kg

kg_doc = {
    "meta": {},
    "nodes": [
        {
            "id": "call:agent:run-001",
            "node_type": "AgentCall",
            "agentId": "triage",
            "input": "Ticket #42: login fails",
        },
        {
            "id": "call:tool:run-001-1",
            "node_type": "ToolCall",
            "toolId": "search_kb",
            "input": {"query": "login failure SSO"},
        },
    ],
    "edges": [
        {"src": "call:agent:run-001", "dst": "call:tool:run-001-1", "rel": "invoked"}
    ],
}

mas_spec = {
    "version": "v1.0.0",
    "agents": [
        {
            "id": "triage",
            "role": "Triage Agent",
            "intent": "Classify tickets.",
            "capabilities": ["intent_classification"],
            "skills": [],
            "tools": ["tool:search_kb"],
        }
    ],
    "tools": [
        {
            "id": "search_kb",
            "in_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            "out_schema": {"type": "array", "items": {"type": "string"}},
        }
    ],
}

result = merge_spec_into_kg(kg_doc, mas_spec)

# Spec nodes are interned
spec_ids = {n["id"] for n in result["nodes"]}
assert "spec:agent:triage" in spec_ids
assert "spec:tool:search_kb" in spec_ids

# Conformance edges are present
edge_rels = {(e["src"], e["rel"], e["dst"]) for e in result["edges"]}
assert ("call:agent:run-001",   "instanceOf", "spec:agent:triage")    in edge_rels
assert ("call:tool:run-001-1",  "invokes",    "spec:tool:search_kb")  in edge_rels

# Meta is updated
assert result["meta"]["spec_injected"] is True
assert result["meta"]["spec_node_count"] == 2
```

### Example 2 — Idempotent re-injection and alternative field names

```python
from mas.library.kg import merge_spec_into_kg

kg_doc = {
    "meta": {},
    "nodes": [
        # Uses snake_case field variants
        {"id": "c1", "node_type": "ToolCall",  "tool_name": "search_kb"},
        {"id": "c2", "node_type": "LLMCall",   "agent_id":  "resolver"},
    ],
    "edges": [],
}

spec = {
    "version": "v2.0.0",
    "agents": [{"id": "resolver", "role": "Resolver", "intent": "Resolve.", "capabilities": [], "skills": [], "tools": []}],
    "tools":  [{"id": "search_kb", "in_schema": {}, "out_schema": {}}],
}

# First injection
merge_spec_into_kg(kg_doc, spec)
node_count_after_first = len(kg_doc["nodes"])
edge_count_after_first = len(kg_doc["edges"])

# Second injection must be idempotent — no duplicates
merge_spec_into_kg(kg_doc, spec)
assert len(kg_doc["nodes"]) == node_count_after_first
assert len(kg_doc["edges"]) == edge_count_after_first

# Conformance via alternative field names works
edge_rels = {(e["src"], e["rel"], e["dst"]) for e in kg_doc["edges"]}
assert ("c1", "invokes",    "spec:tool:search_kb") in edge_rels
assert ("c2", "instanceOf", "spec:agent:resolver") in edge_rels
```

---

## ASCII Diagram

The diagram below shows a single-run KG document after `merge_spec_into_kg`.
Spec nodes (left column) are shared across all runs of the same spec version.
Runtime nodes (right column) record what happened in one specific execution.

```
SPEC SUB-GRAPH (shared / interned)          RUNTIME SUB-GRAPH (per-run)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                                                                         
 ┌──────────────────────┐                   ┌──────────────────────┐    
 │ IntentSpec           │                   │ Message (user input) │    
 │ id=spec:intent:mas   │                   │ id=msg:run-042:0     │    
 └──────────────────────┘                   └──────────┬───────────┘    
                                                       │ triggers       
 ┌──────────────────────┐  ◄────instanceOf──  ┌────────▼───────────┐    
 │ AgentSpec            │                   │ AgentCall            │    
 │ id=spec:agent:triage │                   │ id=call:agent:r42:1  │    
 └──────────┬───────────┘                   └────────┬─────────────┘    
            │ mayInvoke                              │ invoked           
            ▼                                        ▼                   
 ┌──────────────────────┐  ◄────invokes──────  ┌────────────────────┐   
 │ ToolSpec             │                      │ ToolCall           │   
 │ id=spec:tool:srch_kb │                      │ id=call:tool:r42:2 │   
 └──────────────────────┘                      └────────────────────┘   
                                                                         
 ┌──────────────────────┐  ◄────instanceOf──  ┌────────────────────┐    
 │ AgentSpec            │                      │ LLMCall            │    
 │ id=spec:agent:resolv │                      │ id=llm:r42:3       │    
 └──────────┬───────────┘                      └────────────────────┘    
            │ mayInvoke                                                   
            ▼                                                             
 ┌──────────────────────┐  ◄────invokes──────  ┌────────────────────┐   
 │ ToolSpec             │                      │ ToolCall           │   
 │ id=spec:tool:submit  │                      │ id=call:tool:r42:4 │   
 └──────────────────────┘                      └────────────────────┘   
                                                                         
 ┌──────────────────────┐                                                
 │ SkillSpec            │  (no runtime match in this run)               
 │ id=spec:skill:summar │                                                
 └──────────────────────┘                                                
```

Key:
- `────instanceOf──►` conformance edge: runtime AgentCall / LLMCall → AgentSpec
- `────invokes──────►` conformance edge: runtime ToolCall → ToolSpec
- `────mayInvoke────►` design-time declaration edge (inside spec sub-graph)

---

## Stable IDs

All spec node IDs follow a deterministic naming scheme:

| Node type | ID pattern |
|-----------|-----------|
| `IntentSpec` | `spec:intent:mas` (singleton per KG) |
| `AgentSpec` | `spec:agent:{agent["id"]}` |
| `ToolSpec` | `spec:tool:{tool["id"]}` |
| `SkillSpec` | `spec:skill:{skill["id"]}` |

Stability is guaranteed as long as the `"id"` values within the spec entries
remain constant.  The `version` field changes when content changes, but the
node `id` does not — allowing embeddings and cross-document references to
survive version bumps.

### What Stable IDs Enable

**Deduplication**
: `merge_spec_into_kg` uses a simple `id`-set membership check to intern nodes.
  No hashing of full node content is required at merge time.

**Embedding reuse**
: A vector store keyed by node `id` does not need to be re-indexed when new
  runtime data arrives.  Only spec nodes whose `version` changed require a
  re-embed.

**Cross-run lookup**
: Given any `AgentCall.agentId = "triage"` across any run, the spec node is
  always retrievable at the key `spec:agent:triage` — no join table required.

**Graph traversal shortcuts**
: Tools that navigate the KG can hard-code spec entry points (e.g., start at
  `spec:intent:mas` and follow `mayInvoke` edges) without scanning the full
  node list.

---

## Extending the Spec

### Optional Fields and Custom Fields

The spec dict accepts arbitrary additional keys at any level.  Fields not
recognised by the module are ignored during node construction but can be stored
as custom metadata by the caller:

```python
spec = {
    "version": "v1.1.0",
    "agents": [
        {
            "id": "researcher",
            "role": "Research Agent",
            "intent": "Gather evidence from external sources.",
            "capabilities": ["web_search", "pdf_parse"],
            "skills": [],
            "tools": ["tool:browser"],
            # Custom fields — ignored by build_spec_nodes but preserved in spec dict
            "owner": "platform-team",
            "sla_ms": 3000,
            "tags": ["external", "io-heavy"],
        }
    ],
    "tools": [
        {
            "id": "browser",
            "in_schema": {"type": "object", "properties": {"url": {"type": "string"}}},
            "out_schema": {"type": "string"},
            # Custom field
            "rate_limit_rps": 2,
        }
    ],
}

nodes, edges = build_spec_nodes(spec)
# nodes[0] is AgentSpec with standard fields only; custom fields are not in KG node
# but remain accessible via the original spec dict
```

To store custom fields in KG nodes, post-process the returned list:

```python
nodes, edges = build_spec_nodes(spec)
# Annotate AgentSpec nodes with custom metadata
id_to_extra = {
    f"spec:agent:{a['id']}": {k: a[k] for k in a if k not in
        ("id", "role", "intent", "capabilities", "skills", "tools")}
    for a in spec.get("agents", [])
}
for node in nodes:
    if node["id"] in id_to_extra:
        node.update(id_to_extra[node["id"]])
```

### What Happens When No Match Is Found

When `merge_spec_into_kg` encounters a runtime node whose identifier does not
match any spec entry, it silently skips conformance edge creation for that node.
No warning is raised.  The runtime node remains in the graph without any
`instanceOf` or `invokes` edge.

This is intentional: runtime graphs may contain ad-hoc tool calls or agent
invocations introduced during debugging or experimentation that were never
declared in the spec.  Absence of a conformance edge is itself a signal worth
querying:

```python
# Find ToolCall nodes that have no invokes edge (undeclared tool usage)
spec_tool_ids = {n["id"] for n in kg_doc["nodes"] if n["node_type"] == "ToolSpec"}
nodes_with_invokes = {e["src"] for e in kg_doc["edges"] if e["rel"] == "invokes"}
undeclared_calls = [
    n for n in kg_doc["nodes"]
    if n["node_type"] == "ToolCall" and n["id"] not in nodes_with_invokes
]
```

### Using `"goal"` Instead of `"intent"`

If your spec uses `"goal"` as the key for the system purpose, the module treats
it identically to `"intent"`:

```python
spec = {"goal": "Classify and route support tickets."}
nodes, _ = build_spec_nodes(spec)
assert nodes[0]["node_type"] == "IntentSpec"
assert nodes[0]["content"] == "Classify and route support tickets."
```

When both `"intent"` and `"goal"` are present, `"intent"` takes precedence.

### Auto-generated Version Fingerprint

When `"version"` is omitted, the module produces a 12-character hex fingerprint:

```python
import hashlib, json

spec = {"intent": "Do something useful."}
fingerprint = hashlib.sha256(repr(spec).encode()).hexdigest()[:12]
nodes, _ = build_spec_nodes(spec)
assert nodes[0]["version"] == fingerprint
```

The fingerprint changes when any part of the spec changes, making it a reliable
cache-busting key.  If you need version stability across Python versions or
platforms (where `repr` output may differ for floats or complex objects), supply
an explicit `"version"` string instead.
