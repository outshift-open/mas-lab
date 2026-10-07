# KG Query Layer — Reference & Examples

**Module:** `mas.library.kg.core.query`  
**Top-level imports:** `from mas.library.kg import KGIndex, FacetQuery, KGSource, KGView`

---

## Overview

The `mas-library-kg` query layer provides four pure-Python classes for loading,
filtering, indexing, and searching knowledge graphs produced by multi-agent system
(MAS) executions. A *knowledge graph* (`kg.jsonld`) is the canonical record of a single
agent run: it captures every AgentCall, LLMCall, ToolCall, and supporting node in a
`{nodes, edges}` JSON document along with the edges that encode delegation, containment,
and state-transition relationships. The query layer operates entirely on these raw dicts
— no Neo4j driver, no network I/O, no external dependencies — making it fast to import
and easy to embed in notebooks, evaluation scripts, and CI pipelines.

---

## Edge format note

Edges in `kg.jsonld` documents may use one of three key conventions depending on which
version of the event-normalization pipeline produced the file:

| Canonical (preferred) | Legacy alias | Second legacy alias |
|-----------------------|--------------|---------------------|
| `from_id`             | `source`     | `from`              |
| `to_id`               | `target`     | `to`                |
| `edge_type`           | `type`       | —                   |

All four classes in this module transparently handle every variant. When constructing
your own dicts or tests, prefer `from_id` / `to_id` / `edge_type`. When filtering by
edge type, always pass the `edge_type` string value (e.g. `"contains"`).

Common edge types found in real KGs:

| Edge type        | Meaning                                           |
|------------------|---------------------------------------------------|
| `contains`       | Parent call contains a child call                 |
| `hasCall`        | Session or Agent node links to an AgentCall       |
| `leadsTo`        | One AgentCall delegates to the next               |
| `contributesTo`  | A ContextContribution flows into a call           |
| `annotates`      | A CallAnnotation annotates a call node            |
| `realizes`       | A Transition realizes an AgentCall                |
| `fromState`      | Transition's origin State                         |
| `toState`        | Transition's destination State                    |
| `ofToolType`     | ToolCall links to its catalog Tool node           |
| `ofLLMType`      | LLMCall links to its catalog LLM node             |
| `invokesSkill`   | ToolCall that invokes a skill                     |
| `executedBy`     | Call executed by a Worker                         |

---

## `KGIndex`

### Purpose

`KGIndex` is a lightweight, O(1) in-memory graph index. It pre-indexes all nodes by
`id` and `node_type`, and all edges by their source and target, so that typed lookups
and adjacency queries never require a linear scan. It is the right tool when you need
to traverse the graph (walk parent/child relationships, follow delegation chains, find
the root of an execution tree).

`KGIndex` does not filter — it always holds all nodes and edges passed to it. Use
`KGSource` to produce a filtered subgraph first, then hand the result to `KGIndex`.

### Constructors

| Method | Signature | Description |
|--------|-----------|-------------|
| `KGIndex(nodes, edges)` | `__init__(nodes: list[dict], edges: list[dict])` | Build from raw lists. |
| `KGIndex.from_doc(doc)` | `classmethod(doc: dict) -> KGIndex` | Build from a `kg.jsonld` dict (reads `doc["nodes"]` and `doc["edges"]`). |

### Properties

| Property | Return type | Description |
|----------|-------------|-------------|
| `session` | `dict \| None` | The single `Session` node, or `None` if absent. |
| `agent_calls` | `list[dict]` | All nodes with `node_type == "AgentCall"`. |
| `llm_calls` | `list[dict]` | All nodes with `node_type == "LLMCall"`. |
| `tool_calls` | `list[dict]` | All nodes with `node_type == "ToolCall"`. |
| `calls_by_time` | `list[dict]` | All AgentCall, LLMCall, ToolCall, and ProcessingCall nodes sorted by `startTime` ascending. |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `nodes_of_type` | `(ntype: str) -> list[dict]` | All nodes whose `node_type` equals `ntype`. Returns `[]` if none found. |
| `node` | `(nid: str) -> dict \| None` | Exact node lookup by `id`. Returns `None` if not found. |
| `out_neighbors` | `(nid: str, edge_type: str \| None = None) -> list[dict]` | Nodes reachable from `nid`. Optionally restrict by `edge_type`. |
| `in_neighbors` | `(nid: str, edge_type: str \| None = None) -> list[dict]` | Nodes with an edge pointing into `nid`. Optionally restrict by `edge_type`. |
| `find_root_agent_call` | `(agent_id: str \| None = None) -> dict \| None` | Find the outermost AgentCall. Without `agent_id`, returns the AgentCall with no `parentCallId`. With `agent_id`, returns the earliest AgentCall for that agent. Falls back to the globally earliest AgentCall if the `agent_id` is not found. |

### Examples

**Example 1 — Load and inspect a KG**

```python
import json
from mas.library.kg import KGIndex

with open("path/to/kg.jsonld") as f:
    kg_doc = json.load(f)

idx = KGIndex.from_doc(kg_doc)

print("Session ID:", idx.session["sessionId"] if idx.session else "none")
print("AgentCalls:", len(idx.agent_calls))
print("LLMCalls:  ", len(idx.llm_calls))
print("ToolCalls: ", len(idx.tool_calls))
```

**Example 2 — Walk the call tree from the root**

```python
from mas.library.kg import KGIndex

idx = KGIndex.from_doc(kg_doc)

root = idx.find_root_agent_call()
print(f"Root agent: {root['agentId']}  id={root['id']}")

# Direct children of the root AgentCall
children = idx.out_neighbors(root["id"], edge_type="contains")
for child in children:
    print(f"  {child['node_type']}  {child['id']}  agent={child.get('agentId','')}")
```

**Example 3 — Traverse a delegation chain**

```python
from mas.library.kg import KGIndex

idx = KGIndex.from_doc(kg_doc)

def walk(nid: str, depth: int = 0) -> None:
    node = idx.node(nid)
    if node is None:
        return
    indent = "  " * depth
    print(f"{indent}{node['node_type']}  {node.get('agentId', '')}  id={nid}")
    for child in idx.out_neighbors(nid, edge_type="contains"):
        walk(child["id"], depth + 1)

root = idx.find_root_agent_call()
if root:
    walk(root["id"])
```

**Example 4 — Find the parent call for every ToolCall**

```python
from mas.library.kg import KGIndex

idx = KGIndex.from_doc(kg_doc)

for tc in idx.tool_calls:
    parents = idx.in_neighbors(tc["id"], edge_type="contains")
    parent_label = parents[0]["id"] if parents else "—"
    print(f"{tc.get('toolName','?'):30s}  parent={parent_label}")
```

**Example 5 — List all calls in chronological order**

```python
from mas.library.kg import KGIndex
import datetime

idx = KGIndex.from_doc(kg_doc)

for call in idx.calls_by_time:
    ts = call.get("startTime") or 0
    dt = datetime.datetime.fromtimestamp(ts).isoformat(timespec="seconds")
    print(f"{dt}  {call['node_type']:15s}  {call.get('agentId',''):20s}  {call['id'][:8]}")
```

---

## `FacetQuery`

### Purpose

`FacetQuery` is a lightweight, immutable dataclass that describes a filter to be applied
to a `kg.jsonld` document. It is the parameter type consumed by `KGSource.subgraph()` and
`KGSource.load()`. All fields are optional; an omitted field (or `None`) means "no
constraint on that dimension."

`FacetQuery` is JSON-serializable through `to_dict()` / `from_dict()`, which makes it
easy to store alongside experiment configs or pass over a network API.

### Constructor

```python
@dataclass
class FacetQuery:
    session_id:  str | None              = None
    run_id:      str | None              = None
    agent_ids:   list[str] | None        = None
    call_types:  list[str] | None        = None
    node_types:  list[str] | None        = None
    edge_types:  list[str] | None        = None
    time_range:  tuple[float, float] | None = None
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str \| None` | Keep only nodes whose `sessionId` matches (case-insensitive). Nodes with no `sessionId` field are always kept. |
| `run_id` | `str \| None` | Keep only nodes whose `runId` matches (case-insensitive). Nodes with no `runId` field are always kept. |
| `agent_ids` | `list[str] \| None` | Keep only call nodes whose `agentId` is in this list (case-insensitive). Non-call nodes are always kept. |
| `call_types` | `list[str] \| None` | Convenience alias for node-type filtering restricted to known call types. E.g. `["LLMCall", "ToolCall"]` keeps those call types and drops other call types, but leaves all non-call nodes unchanged. |
| `node_types` | `list[str] \| None` | Explicit node_type whitelist. Merged with `call_types` when both are set. |
| `edge_types` | `list[str] \| None` | Keep only edges whose `edge_type` is in this list. Applied after node filtering; dangling edges are always removed. |
| `time_range` | `tuple[float, float] \| None` | `(t0, t1)` in Unix epoch seconds. Keep nodes whose time window `[startTime, endTime]` overlaps `[t0, t1]`. |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `to_dict` | `() -> dict` | Serialize to a plain dict. Fields that are `None` are omitted. |
| `FacetQuery.from_dict` | `classmethod(d: dict) -> FacetQuery` | Deserialize from a dict. Accepts both `snake_case` and `camelCase` key names. |

### `call_types` vs `node_types`

`call_types` is a convenience field that maps directly to node type names but applies
only within the set of recognized call node types:

```
AgentCall, LLMCall, ToolCall, SkillCall,
ProcessingCall, ThinkingCall, MITMCall, MASCall, TaskCall
```

When you pass `call_types=["LLMCall", "ToolCall"]`, non-call nodes (Session, State,
Transition, Agent, Tool, …) are not filtered out. This makes it safe to extract a
"calls only" view without accidentally stripping the structural backbone.

When both `call_types` and `node_types` are set, their allowed type sets are unioned.

### Examples

**Example 1 — Filter by session and agent**

```python
from mas.library.kg import FacetQuery

q = FacetQuery(
    session_id="session-abc-123",
    agent_ids=["orchestrator", "analyst"],
)
```

**Example 2 — LLM and Tool calls only in a time window**

```python
from mas.library.kg import FacetQuery

q = FacetQuery(
    call_types=["LLMCall", "ToolCall"],
    time_range=(1_716_000_000.0, 1_716_000_060.0),
)
```

**Example 3 — Serialize and deserialize (snake_case and camelCase both work)**

```python
from mas.library.kg import FacetQuery

q = FacetQuery(session_id="s1", agent_ids=["cra"], time_range=(0.0, 100.0))
d = q.to_dict()
# {"session_id": "s1", "agent_ids": ["cra"], "time_range": [0.0, 100.0]}

# Round-trip with snake_case keys
q2 = FacetQuery.from_dict(d)
assert q2 == q

# Also works with camelCase (e.g., from a JavaScript client)
q3 = FacetQuery.from_dict({"sessionId": "s1", "agentIds": ["cra"], "timeRange": [0.0, 100.0]})
assert q3.session_id == "s1"
```

**Example 4 — Restrict to specific edge types**

```python
from mas.library.kg import FacetQuery

# Keep only containment edges (drops contributesTo, annotates, etc.)
q = FacetQuery(edge_types=["contains", "hasCall"])
```

**Example 5 — Store a query config in JSON**

```python
import json
from mas.library.kg import FacetQuery

config = {
    "sessionId": "my-session",
    "callTypes": ["AgentCall", "LLMCall"],
    "timeRange": [1_716_000_000.0, 1_716_003_600.0],
}

# Save to disk
with open("filter.json", "w") as f:
    json.dump(config, f, indent=2)

# Reload later
with open("filter.json") as f:
    q = FacetQuery.from_dict(json.load(f))
```

---

## `KGSource`

### Purpose

`KGSource` is the data-access layer that applies a `FacetQuery` to a `kg.jsonld` document
and returns a filtered `{nodes, edges, run_id, meta}` subgraph dict. It is the entry
point for any pipeline that needs to narrow a full execution trace to a relevant slice
before further analysis or indexing.

Unlike `KGIndex`, `KGSource` does not build any in-memory index — it operates directly
on the raw lists and is inexpensive to construct.

### Constructors

| Method | Signature | Description |
|--------|-----------|-------------|
| `KGSource(kg_doc)` | `__init__(kg: dict)` | Wrap an already-loaded `kg.jsonld` dict. |
| `KGSource.from_file(path)` | `classmethod(path: str \| Path) -> KGSource` | Read a `kg.jsonld` file from disk (UTF-8). Expands `~` and resolves symlinks. |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `subgraph` | `(query: FacetQuery \| None = None) -> dict` | Return a filtered `{nodes, edges, run_id, meta}` dict. With `query=None` returns the full document (shallow copy). |
| `load` | `(query: FacetQuery \| None = None) -> tuple[list[dict], list[dict]]` | Convenience wrapper: returns `(nodes, edges)` after applying the query. |

### Filtering order

Filters are applied sequentially in a fixed order. A node must survive every active
filter to remain in the output. Edges are always filtered last and any edge whose
source or target was removed by a prior step is dropped automatically.

```
1. node_types / call_types  — node-type whitelist
2. agent_ids                — call nodes must match agentId
3. session_id               — nodes with sessionId must match
4. run_id                   — nodes with runId must match
5. time_range               — startTime/endTime must overlap window
6. edge_types               — edge-type whitelist
7. dangling edge removal    — edges with missing endpoints are dropped
```

### Examples

**Example 1 — Load from file and extract a full subgraph**

```python
from mas.library.kg import KGSource

src = KGSource.from_file("/data/runs/run-001/kg.jsonld")
sub = src.subgraph()

print(f"Nodes: {len(sub['nodes'])}  Edges: {len(sub['edges'])}")
```

**Example 2 — Filter to calls from a single agent**

```python
from mas.library.kg import KGSource, FacetQuery

src = KGSource.from_file("kg.jsonld")
nodes, edges = src.load(
    FacetQuery(
        agent_ids=["moderator"],
        call_types=["AgentCall", "LLMCall", "ToolCall"],
    )
)

print(f"Kept {len(nodes)} call nodes from agent 'moderator'")
```

**Example 3 — Slice a time window for replay analysis**

```python
from mas.library.kg import KGSource, FacetQuery

src = KGSource.from_file("kg.jsonld")

# Examine only the first 30 seconds of the run
sub = src.subgraph(FacetQuery(time_range=(1_716_000_000.0, 1_716_000_030.0)))
print(f"Nodes in first 30 s: {len(sub['nodes'])}")
```

**Example 4 — Extract only structural nodes (no call nodes)**

```python
from mas.library.kg import KGSource, FacetQuery

src = KGSource.from_file("kg.jsonld")

sub = src.subgraph(
    FacetQuery(node_types=["Session", "Agent", "State", "Transition"])
)
print("Structural node types:", {n["node_type"] for n in sub["nodes"]})
```

**Example 5 — Chain two filters: agents then time**

```python
from mas.library.kg import KGSource, FacetQuery

src = KGSource.from_file("kg.jsonld")

# A single FacetQuery applies all active filters in one pass
q = FacetQuery(
    agent_ids=["orchestrator"],
    call_types=["LLMCall"],
    time_range=(1_716_000_010.0, 1_716_000_050.0),
)
nodes, edges = src.load(q)

print(f"LLMCalls from orchestrator in window: {len(nodes)}")
```

**Example 6 — Keep only containment edges and inspect**

```python
from mas.library.kg import KGSource, FacetQuery

src = KGSource.from_file("kg.jsonld")
sub = src.subgraph(FacetQuery(edge_types=["contains"]))

print(f"Edges remaining after edge_types filter: {len(sub['edges'])}")
# All remaining edges will have edge_type == "contains"
for e in sub["edges"][:5]:
    print(e["from_id"], "->", e["to_id"])
```

---

## `KGView`

### Purpose

`KGView` is a predicate-based search layer over a flat list of KG nodes. It is
optimized for repeated queries of the form "give me all nodes of type X where field Y
equals Z." It is the right tool when you are exploring or analyzing node attributes
rather than traversing edges. For edge traversal, combine it with `KGIndex`.

`KGView` pre-indexes nodes by `node_type` and `id` at construction time, so individual
`query()` and `get()` calls are fast.

### Constructors

| Method | Signature | Description |
|--------|-----------|-------------|
| `KGView(nodes)` | `__init__(nodes: list[dict])` | Build from a raw list of node dicts. |
| `KGView.from_kg(kg_doc)` | `classmethod(kg: dict) -> KGView` | Build from a `kg.jsonld` dict (reads `kg["nodes"]`). |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `query` | `(node_type: str, **field_filters) -> list[dict]` | Return all nodes of `node_type` matching every keyword filter. Results are sorted by `startTime` ascending. |
| `get` | `(node_id: str \| None) -> dict \| None` | Return the node with the given `id`, or `None`. Passing `None` also returns `None`. |
| `types` | `() -> list[str]` | Return all `node_type` values present in this view. |

### `query()` field filter semantics

Each keyword argument to `query()` is matched against the corresponding field of the
node dict:

| Filter value type | Matching behavior |
|-------------------|-------------------|
| `str` | Case-insensitive equality: `str(field_value).lower() == filter_value.lower()` |
| `None` | Field is absent or empty string: `field_value in (None, "")` |
| Any callable | Called as `predicate(field_value)` — return `True` to keep the node |
| Any other type | Strict equality: `field_value == filter_value` |

All filters must match simultaneously (logical AND). Passing no keyword arguments
returns all nodes of the specified type.

### Examples

**Example 1 — All LLM calls in chronological order**

```python
from mas.library.kg import KGView

view = KGView.from_kg(kg_doc)

for call in view.query("LLMCall"):
    print(call["id"], call.get("modelName"), call.get("startTime"))
```

**Example 2 — Root AgentCalls (no parentCallId)**

```python
from mas.library.kg import KGView

view = KGView.from_kg(kg_doc)

# Passing None matches fields that are absent or empty string
root_calls = view.query("AgentCall", parentCallId=None)
print(f"Root agent calls: {len(root_calls)}")
```

**Example 3 — Tool calls for a specific agent (case-insensitive)**

```python
from mas.library.kg import KGView

view = KGView.from_kg(kg_doc)

# "SRE", "sre", "Sre" all match
sre_tools = view.query("ToolCall", agentId="sre")
for tc in sre_tools:
    print(f"  {tc.get('toolName'):30s}  {tc['id'][:8]}")
```

**Example 4 — Find calls matching a custom predicate**

```python
from mas.library.kg import KGView

view = KGView.from_kg(kg_doc)

# LLMCalls whose input was longer than 500 characters
long_inputs = view.query(
    "LLMCall",
    inputContent=lambda v: isinstance(v, str) and len(v) > 500,
)
print(f"Long-context LLM calls: {len(long_inputs)}")
```

**Example 5 — Inspect present node types**

```python
from mas.library.kg import KGView

view = KGView.from_kg(kg_doc)

print("Node types in this KG:")
for t in sorted(view.types()):
    count = len(view.query(t))
    print(f"  {t:25s}  {count:4d}")
```

**Example 6 — Get a specific node by ID**

```python
from mas.library.kg import KGView

view = KGView.from_kg(kg_doc)

call_id = "c608346f-9c67-45e7-bfb9-de37ddf3e722"
node = view.get(call_id)
if node:
    print(f"Found: {node['node_type']}  agent={node.get('agentId')}")
else:
    print("Node not found")
```

---

## Common patterns

### Pattern 1 — Filter with KGSource, then index with KGIndex

`KGSource` and `KGIndex` complement each other: `KGSource` narrows the data, `KGIndex`
makes it traversable. The handoff is a plain subgraph dict.

```python
from mas.library.kg import KGSource, KGIndex, FacetQuery

# Step 1: load and filter
src = KGSource.from_file("kg.jsonld")
sub = src.subgraph(
    FacetQuery(agent_ids=["orchestrator"], call_types=["AgentCall", "LLMCall", "ToolCall"])
)

# Step 2: index the filtered subgraph for graph traversal
idx = KGIndex.from_doc(sub)

root = idx.find_root_agent_call("orchestrator")
print(f"Orchestrator root call: {root['id']}")

children = idx.out_neighbors(root["id"], edge_type="contains")
print(f"Direct children: {len(children)}")
```

### Pattern 2 — Filter with KGSource, then query attributes with KGView

When you don't need to traverse edges but want to search and filter nodes by their
fields, hand the subgraph to `KGView`.

```python
from mas.library.kg import KGSource, KGView, FacetQuery

src = KGSource.from_file("kg.jsonld")
sub = src.subgraph(FacetQuery(time_range=(1_716_000_000.0, 1_716_000_300.0)))

view = KGView(sub["nodes"])

# Find all tool calls to "search" in this time window
search_calls = view.query("ToolCall", toolName="search")
print(f"'search' tool calls in first 5 min: {len(search_calls)}")
```

### Pattern 3 — Use KGIndex and KGView together for annotated traversal

Build both from the same (optionally filtered) subgraph and use each for what it's
good at: `KGIndex` for edges, `KGView` for node lookups.

```python
from mas.library.kg import KGSource, KGIndex, KGView, FacetQuery

src = KGSource.from_file("kg.jsonld")
sub = src.subgraph()

idx = KGIndex.from_doc(sub)
view = KGView(sub["nodes"])

# Walk each AgentCall and report its LLM children
for agent_call in view.query("AgentCall"):
    llm_children = [
        n for n in idx.out_neighbors(agent_call["id"], edge_type="contains")
        if n.get("node_type") == "LLMCall"
    ]
    print(f"{agent_call['agentId']:20s}  LLM calls: {len(llm_children)}")
```

### Pattern 4 — Multi-agent comparative analysis

Compare how much each agent contributed in a single run by slicing per agent.

```python
from mas.library.kg import KGSource, KGView, FacetQuery

src = KGSource.from_file("kg.jsonld")

# Discover which agents appear in this KG
full_view = KGView.from_kg(src.subgraph())
all_agents = {n.get("agentId") for n in full_view.query("AgentCall") if n.get("agentId")}

for agent_id in sorted(all_agents):
    nodes, _ = src.load(
        FacetQuery(
            agent_ids=[agent_id],
            call_types=["AgentCall", "LLMCall", "ToolCall"],
        )
    )
    agent_view = KGView(nodes)
    print(
        f"{agent_id:20s}  "
        f"AgentCalls={len(agent_view.query('AgentCall'))}  "
        f"LLMCalls={len(agent_view.query('LLMCall'))}  "
        f"ToolCalls={len(agent_view.query('ToolCall'))}"
    )
```

### Pattern 5 — FacetQuery round-trip with a config file

Store filter presets in JSON and restore them at runtime. Useful for reproducible
evaluation scripts that need consistent filtering across multiple runs.

```python
import json
from mas.library.kg import KGSource, FacetQuery

# Load a stored filter preset (camelCase from a JS-generated config is fine)
with open("experiment-filter.json") as f:
    preset = json.load(f)  # e.g. {"agentIds": ["cra"], "callTypes": ["LLMCall"]}

q = FacetQuery.from_dict(preset)

for run_path in sorted(Path("runs/").glob("*/kg.jsonld")):
    src = KGSource.from_file(run_path)
    nodes, edges = src.load(q)
    print(f"{run_path.parent.name:30s}  nodes={len(nodes):4d}  edges={len(edges):4d}")
```

### Pattern 6 — Build a delegation tree with KGIndex

Reconstruct the full parent/child AgentCall hierarchy as a nested dict using
`find_root_agent_call` and recursive `out_neighbors`.

```python
from mas.library.kg import KGIndex

idx = KGIndex.from_doc(kg_doc)

def build_tree(nid: str) -> dict:
    node = idx.node(nid)
    return {
        "id": nid,
        "agentId": node.get("agentId", "") if node else "",
        "node_type": node.get("node_type", "") if node else "",
        "children": [
            build_tree(child["id"])
            for child in idx.out_neighbors(nid, edge_type="contains")
            if child.get("node_type") == "AgentCall"
        ],
    }

root = idx.find_root_agent_call()
if root:
    import json
    print(json.dumps(build_tree(root["id"]), indent=2))
```

### Pattern 7 — Verify edge consistency after a custom filter

When you apply a node filter manually outside of `KGSource`, use `KGIndex` to verify
that all edge endpoints are still present in your working set.

```python
from mas.library.kg import KGSource, KGIndex, FacetQuery

src = KGSource.from_file("kg.jsonld")

# KGSource always removes dangling edges automatically
sub = src.subgraph(FacetQuery(node_types=["AgentCall", "LLMCall"]))
idx = KGIndex.from_doc(sub)

kept_ids = {n["id"] for n in sub["nodes"]}
dangling = [
    e for e in sub["edges"]
    if e.get("from_id") not in kept_ids or e.get("to_id") not in kept_ids
]
print(f"Dangling edges (should be 0): {len(dangling)}")
```

---

## Full `kg.jsonld` document structure

A minimal valid `kg.jsonld` document that all four classes can consume:

```json
{
  "run_id": "my-run-001",
  "meta": {
    "events": 12,
    "nodes": 6,
    "edges": 3,
    "source": "events.jsonl"
  },
  "nodes": [
    {
      "id": "sess-1",
      "node_type": "Session",
      "sessionId": "sess-1",
      "runId": "my-run-001",
      "startTime": 1716000000.0,
      "endTime": 1716000060.0,
      "inputQuery": "What is the weather in Paris?",
      "finalResponse": "The weather is sunny."
    },
    {
      "id": "ac-1",
      "node_type": "AgentCall",
      "callId": "ac-1",
      "agentId": "orchestrator",
      "agentName": "orchestrator",
      "sessionId": "sess-1",
      "runId": "my-run-001",
      "parentCallId": "",
      "startTime": 1716000001.0,
      "endTime": 1716000055.0
    },
    {
      "id": "llm-1",
      "node_type": "LLMCall",
      "callId": "llm-1",
      "agentId": "orchestrator",
      "sessionId": "sess-1",
      "runId": "my-run-001",
      "parentCallId": "ac-1",
      "startTime": 1716000002.0,
      "endTime": 1716000010.0,
      "modelName": "azure/gpt-4o",
      "inputContent": "What is the weather in Paris?",
      "outputContent": "I will call the weather tool."
    },
    {
      "id": "tc-1",
      "node_type": "ToolCall",
      "callId": "tc-1",
      "agentId": "orchestrator",
      "sessionId": "sess-1",
      "runId": "my-run-001",
      "parentCallId": "llm-1",
      "startTime": 1716000011.0,
      "endTime": 1716000020.0,
      "toolName": "get_weather",
      "inputContent": "{\"city\": \"Paris\"}",
      "outputContent": "Sunny, 22°C"
    }
  ],
  "edges": [
    {"edge_type": "contains", "from_id": "ac-1",  "to_id": "llm-1"},
    {"edge_type": "contains", "from_id": "llm-1", "to_id": "tc-1"},
    {"edge_type": "hasCall",  "from_id": "sess-1", "to_id": "ac-1"}
  ]
}
```

### Common node fields

| Field | Present on | Description |
|-------|-----------|-------------|
| `id` | All nodes | Unique node identifier |
| `node_type` | All nodes | Node type string (see below) |
| `sessionId` | Most nodes | Parent session identifier |
| `runId` | Most nodes | Run identifier |
| `agentId` | Call nodes | Agent that owns this call |
| `parentCallId` | Call nodes | ID of the enclosing call; root calls have `""` or absent |
| `startTime` | Call nodes | Unix epoch (float seconds) |
| `endTime` | Call nodes | Unix epoch (float seconds) |
| `toolName` | ToolCall | Name of the tool invoked |
| `modelName` | LLMCall | Model identifier (e.g. `"azure/gpt-4o"`) |
| `inputContent` | Call nodes | Input payload (may be truncated) |
| `outputContent` | Call nodes | Output payload (may be truncated) |

### Common node types

| `node_type` | Category | Description |
|-------------|----------|-------------|
| `Session` | Structural | Top-level session record |
| `Run` | Structural | Run metadata node |
| `Agent` | Structural | Agent catalog entry |
| `AgentCall` | Call | One invocation of an agent |
| `LLMCall` | Call | One call to a language model |
| `ToolCall` | Call | One tool or function call |
| `ProcessingCall` | Call | A processing step (design patterns, etc.) |
| `SkillCall` | Call | A skill invocation |
| `ThinkingCall` | Call | An extended-thinking step |
| `State` | State machine | State node in the agent state machine |
| `Transition` | State machine | Edge between two State nodes |
| `ContextContribution` | Annotation | Context segment contributed to a call |
| `CallAnnotation` | Annotation | Rich annotation attached to a call |
| `Tool` | Catalog | Tool catalog entry |
| `LLM` | Catalog | LLM catalog entry |

---

## Quick reference

```python
# Load
from mas.library.kg import KGIndex, FacetQuery, KGSource, KGView
import json

kg_doc = json.loads(open("kg.jsonld").read())

# ---- KGSource ---------------------------------------------------------------
src = KGSource(kg_doc)                         # from dict
src = KGSource.from_file("kg.jsonld")           # from file

sub  = src.subgraph()                          # full graph (dict)
sub  = src.subgraph(FacetQuery(...))           # filtered graph (dict)
nodes, edges = src.load(FacetQuery(...))       # filtered (nodes, edges)

# ---- KGIndex ----------------------------------------------------------------
idx = KGIndex(nodes, edges)                    # from lists
idx = KGIndex.from_doc(sub)                    # from subgraph dict

idx.session                                    # Session node | None
idx.agent_calls                                # list of AgentCall dicts
idx.llm_calls                                  # list of LLMCall dicts
idx.tool_calls                                 # list of ToolCall dicts
idx.calls_by_time                              # all calls sorted by startTime

idx.node("some-id")                            # dict | None
idx.nodes_of_type("State")                     # list[dict]
idx.out_neighbors("nid", edge_type="contains") # list[dict]
idx.in_neighbors("nid", edge_type="contains")  # list[dict]
idx.find_root_agent_call()                     # outermost AgentCall | None
idx.find_root_agent_call("analyst")            # earliest AgentCall for agent

# ---- FacetQuery -------------------------------------------------------------
q = FacetQuery(
    session_id="sess-1",
    run_id="run-001",
    agent_ids=["orchestrator"],
    call_types=["LLMCall", "ToolCall"],
    node_types=["State"],
    edge_types=["contains"],
    time_range=(1716000000.0, 1716000060.0),
)
d = q.to_dict()                                # dict (None fields omitted)
q = FacetQuery.from_dict(d)                    # accepts snake_case + camelCase

# ---- KGView -----------------------------------------------------------------
view = KGView(nodes)                           # from list
view = KGView.from_kg(kg_doc)                  # from dict

view.types()                                   # ["Session", "AgentCall", ...]
view.query("LLMCall")                          # all LLMCall nodes (sorted)
view.query("AgentCall", parentCallId=None)     # root agent calls
view.query("ToolCall", agentId="analyst")      # case-insensitive string match
view.query("LLMCall", inputContent=lambda v: len(v or "") > 200)  # callable
view.get("some-node-id")                       # dict | None
```
